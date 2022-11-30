from odoo import models, fields, api, _
from odoo.addons.vsdc_connector.controllers.api_calls import Messenger
from .utils import Miner, pad_zeroes, success_response, _logger

RRA_PRODUCT_TYPES = [('1', 'Raw Material'), ('2', 'Finished Product'), ('3', 'Service')]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    unspsc_categ_id = fields.Many2one('item.classification', "UNSPSC Category", required=True)
    rra_code = fields.Selection(related='unspsc_categ_id.rra_code')
    classification_code = fields.Char(compute='compute_classification_code', store=True)
    quantity_unit = fields.Many2one('quantity.unit', 'Unit of Quantity', required=True,
                                    default=lambda self: self.env.ref('cis.quantity_unit_kg').id)
    packaging_unit = fields.Many2one('packaging.unit', required=True,
                                     default=lambda self: self.env.ref('cis.packaging_unit_ct').id)
    detailed_type = fields.Selection(selection_add=[
        ('product', 'Storable Product')
    ], tracking=True, default='product', ondelete={'product': 'set consu'})
    origin_country = fields.Many2one('res.country', default=lambda self: self.env.ref('base.rw'), required=True)
    rra_product_type = fields.Selection(RRA_PRODUCT_TYPES, 'RRA Product Type', required=True, default='2')
    inventory_update_time = fields.Datetime(default=fields.Datetime.now, store=True)
    item_code = fields.Char(compute='compute_item_code', string="Product Code", store=True)
    description = fields.Text()
    synced_date = fields.Datetime(help="The date at which the data is synced with VSDC", string="Synced with VSDC at")
    date_sent = fields.Text()
    response = fields.Text()
    sent_to_vsdc = fields.Boolean(default=False)

    @api.onchange('unspsc_categ_id')
    def onchange_unspsc_categ_id(self):
        taxes_id = self.env['account.tax'].sudo().search([('rra_code', '=', self.rra_code), ('type_tax_use', '=', 'sale')])
        if taxes_id:
            self.taxes_id = [taxes_id[0].id]
        else:
            self.taxes_id = False

    @api.depends('product_variant_ids')
    def compute_item_code(self):
        for product in self:
            product.item_code = False
            if len(product.product_variant_ids):
                product.item_code = product.product_variant_ids[0].item_code or ""

    def sdc_send_item(self):
        for product in self:
            product_id = self.env['product.product'].search([('product_tmpl_id', '=', product.id)])
            if product_id:
                res = product_id.sudo().sdc_send_item()
                if res.get('success', False):
                    product.synced_date = product_id.synced_date
                    product.sent_to_vsdc = True
                    product.message_post(body="Item successfully synced with VSDC")
                else:
                    product.message_post(body=res.get('msg'))
                    product.response = res.get('msg')

                product.date_sent = res.get('data', False)
                product.response = res.get('msg', False)



    # @api.model
    # def create(self, vals):
    #     res = super(ProductTemplate, self).create(vals)
    #     product_id = self.env['product.product'].search([('product_tmpl_id', '=', res.id)])
    #     product_id.sdc_send_item()
    #     res.synced_date = product_id.synced_date
    #     res.message_post(body="Item successfully synced with VSDC")
    #     return res

    @api.depends('unspsc_categ_id')
    def compute_classification_code(self):
        for tmpl in self:
            tmpl.classification_code = tmpl.unspsc_categ_id.code if tmpl.unspsc_categ_id else "51000000"

    @api.model
    def action_update_taxes(self):
        products = self.env['product.template'].search([('type', '!=', 'service')])
        sale_products = products.filtered(
            lambda p: not p.taxes_id.filtered(lambda tax: tax.company_id.id == self.env.company.id))
        purchase_products = products.filtered(
            lambda p: not p.supplier_taxes_id.filtered(lambda tax: tax.company_id.id == self.env.company.id))
        if sale_products:
            sale_taxes = self.env['account.tax'].sudo().search(
                [('rra_code', '=', 'B'), ('type_tax_use', '=', 'sale')]).mapped('id')
            sale_products.write({'taxes_id': [(6, 0, sale_taxes)]})
        if purchase_products:
            purchase_taxes = self.env['account.tax'].sudo().search(
                [('rra_code', '=', 'B'), ('type_tax_use', '=', 'purchase')]).mapped('id')
            purchase_products.write({'supplier_taxes_id': [(6, 0, purchase_taxes)]})


class ProductProduct(models.Model):
    _inherit = 'product.product'

    send_inventory = fields.Binary(compute="_send_inventory")
    send_item = fields.Binary(compute="_send_item")
    item_code = fields.Char(compute='compute_item_code', string='Product Code', store=True)
    sent_to_vsdc = fields.Boolean(default=False)
    synced_date = fields.Datetime(help="The date at which the data is synced with VSDC", string="Synced with VSDC at")
    date_sent = fields.Text()
    response = fields.Text()

    def company_qty_available(self, company):
        self.ensure_one()
        warehouses = self.env['stock.warehouse'].search([('company_id', '=', company.id)])
        return sum(self.with_context(warehouse=warehouse.id).qty_available for warehouse in warehouses)

    @api.model
    def create(self, vals):
        product_id = super(ProductProduct, self).create(vals)
        res = product_id.sdc_send_item()
        if res.get('success', False):
            product_id.product_tmpl_id.synced_date = product_id.synced_date
            product_id.product_tmpl_id.sent_to_vsdc = True
            product_id.product_tmpl_id.message_post(body="Item successfully synced with VSDC")
        else:
            product_id.product_tmpl_id.message_post(body=res.get('msg'))

        product_id.product_tmpl_id.date_sent = res.get('data', False)
        product_id.product_tmpl_id.response = res.get('response', "")
        return product_id

    @api.model
    def cron_send_to_vsdc(self):
        pass
        # self.sdc_send_item()
        # self.sdc_send_inventory()

    @api.depends('origin_country', 'packaging_unit', 'quantity_unit', 'rra_product_type')
    def compute_item_code(self):
        for product in self:
            packaging_code = (product.packaging_unit or self.env.ref('cis.packaging_unit_ct')).code
            quantity_code = (product.packaging_unit or self.env.ref('cis.quantity_unit_kg')).code
            product.item_code = f'{product.origin_country.code}{product.rra_product_type}{packaging_code}{quantity_code}{pad_zeroes(product.id, 7)}'

    def _send_inventory(self):
        for product in self:
            data = {}
            # if product.type == 'product':
            #     data = Miner().get_inventory_data(product, self._context.get('sdc_company'), qty=self._context.get('qty'))
            product.send_inventory = data

    def _send_item(self):
        for product in self:
            data = Miner().get_item_data(product, self._context.get('sdc_company'))
            product.send_item = data

    def sdc_send_item(self):
        _logger.info("Executing sdc_send_item...")
        for company in self.env.user.company_ids.filtered(lambda com: com.sdc_base_url):
            dt = fields.Datetime.now()
            if not self:
                return
            try:
                res_data = {"success": False, "msg": "", "data": [], 'response': ""}
                item = self.with_context(sdc_company=company).send_item
                res_data['data'] = item
                self.date_sent = item
                res = Messenger(self.env.user, item, company=company, endpoint='items/saveItems').send_item()
                self.response = res
                res_data['response'] = res
                self.env['sdc.log'].get_or_create(company, 'send_item', res, dt)
                if res.get('resultCd') == '000':
                    self.write({'sent_to_vsdc': True, 'synced_date': dt})
                    res_data['success'] = True
                    msg = res
                else:
                    msg = f"Item Syncing  Failed!\n See detailed response: {res}"
                    self.message_post(body=msg)
                res_data['msg'] = msg

                return res_data
            except Exception as e:
                _logger.error(_(f"{e}"))

    def sdc_send_inventory(self):
        _logger.info("Executing sdc_send_inventory...")
        for company in self.env.user.company_ids.filtered(lambda com: com.sdc_base_url):
            dmn = [('company_id', 'in', (False, company.id)), ('sent_to_vsdc', '!=', False), ('type', '=', 'product')]
            last_request = self.env['sdc.log'].search(
                [('company_id', '=', company.id), ('sid', '=', 'SEND_INVENTORY'), ('type', '=', 'success')], limit=1)
            if last_request:
                dmn.append(('inventory_update_time', '>', last_request.time.strftime('%Y-%m-%d %H:%M:%S')))
            products = self.env['product.product'].search(dmn, limit=100)
            dt = fields.Datetime.now()
            if not products:
                return
            try:
                data = [product.with_context(sdc_company=company).send_inventory for product in products]
                res = Messenger(self.env.user, data, company=company).send_inventory()
                self.env['sdc.log'].get_or_create(company, 'send_inventory', res, dt)
            except Exception as e:
                _logger.error(_(f"{e}"))


class SupplierInfo(models.Model):
    _inherit = 'product.supplierinfo'

    categ_code = fields.Char('Vendor product category',
                             help="This vendor's product category code will be used when printing a request for "
                                  "quotation. Keep empty to use the internal one.")
