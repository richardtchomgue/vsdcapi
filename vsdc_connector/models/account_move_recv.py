from odoo import api, fields, models, _
from odoo.addons.vsdc_connector.controllers.api_calls import Messenger
from odoo.addons.vsdc_connector.models.utils import Miner, _logger, success_response
from odoo.http import request

from odoo.exceptions import UserError, ValidationError


class AccountMoveRecv(models.Model):
    _name = 'account.move.recv'
    _description = 'Received Account Moves'

    def get_default_company(self):
        cookies = request.httprequest.cookies
        cid = self.env.company.id
        if cookies.get('cids'):
            cid = cookies.get('cids').split(',')[0]
        return cid

    company_id = fields.Many2one('res.company', required=True, readonly=True, default=get_default_company)
    name = fields.Char(compute='compute_name', store=True)

    spplrInvcNo = fields.Char('Supplier Invoice Id', required=True)
    spplrTin = fields.Char('Supplier TIN', required=True)
    spplrNm = fields.Char('Supplier Name')
    spplrBhfId = fields.Char('Supplier Branch ID')
    rcptTyCd = fields.Char('Receipt Type Code')
    pmtTyCd = fields.Many2one('vsdc.payment.method', string="Payment Type")
    cfmDt = fields.Char('Validated Date')
    salesDt = fields.Char('Sale Date')
    stockRlsDt = fields.Char('Stock Release Date')
    totItemCnt = fields.Integer('Total Item Count')

    # sdc_rec_id = fields.Integer('VSDC ID', copy=False)
    # bcncSdcId = fields.Char('Supplier SDC ID')
    # bcncMrcNo = fields.Char('Supplier MRC')
    line_ids = fields.One2many('account.move.line.recv', 'move_id', 'Lines')

    taxblAmtA = fields.Float('Taxable Amount A')
    taxblAmtB = fields.Float('Taxable Amount B')
    taxblAmtC = fields.Float('Taxable Amount C')
    taxblAmtD = fields.Float('Taxable Amount D')
    taxRtA = fields.Float('Tax Rate A')
    taxRtB = fields.Float('Tax Rate B')
    taxRtC = fields.Float('Tax Rate C')
    taxRtD = fields.Float('Tax Rate D')
    taxAmtA = fields.Float('Tax Amt A')
    taxAmtB = fields.Float('Tax Amt B')
    taxAmtC = fields.Float('Tax Amt C')
    taxAmtD = fields.Float('Tax Amt D')
    totTaxblAmt = fields.Float('Total Taxable Amount')
    totTaxAmt = fields.Float(string='Total Tax Amount')
    totAmt = fields.Float(string='Total Amount')

    remark = fields.Text('Total Tax Amount')
    synchronized = fields.Boolean(default=False)
    response = fields.Html('Response')
    request = fields.Html('Request')

    @api.depends('spplrTin', 'spplrInvcNo')
    def compute_name(self):
        for rec in self:
            rec.name = '%s(%s)' % (rec.spplrTin, rec.spplrInvcNo)

    @api.model
    def action_fetch_purchases(self):
        cookies = request.httprequest.cookies
        company_id = self.env['res.company'].sudo()
        if cookies.get('cids'):
            cid = cookies.get('cids').split(',')[0]
            if cid:
                company_id = self.env['res.company'].sudo().search([('id', '=', cid)])
        if not company_id.branch_type == 'hq':
            return False
        req_data = {"tin": self.env.company.vat, "bhfId": company_id.vsdc_branch_id.branch_id or self.env.company.branch, "lastReqDt": self.env.company.last_request_date}

        res = Messenger(self.env.user, req_data, company=self.env.company, endpoint='trnsPurchase/selectTrnsPurchaseSales').recv_purchase()
        if isinstance(res, dict) and res.get('resultCd') == "000":
            data = res.get('data', {})
            sale_list = data.get('saleList', [])
            purchases = []
            for sale in sale_list:
                sale_exists = self.search([('spplrInvcNo', '=', sale.get('spplrInvcNo', ''))])
                if not sale_exists:
                    line_list = sale.get('itemList', {})
                    if 'pmtTyCd' in sale:
                        payment_method_exists = self.env['vsdc.payment.method'].sudo().search([('code', '=', sale.get('pmtTyCd', ''))])
                        if payment_method_exists:
                            sale['pmtTyCd'] = payment_method_exists.id
                        else:
                            sale['pmtTyCd'] = False
                    order_lines = []
                    for line in line_list:
                        order_lines.append((0, 0, line))
                    sale.pop('itemList')
                    sale['line_ids'] = order_lines
                    sale['request'] = req_data
                    sale['response'] = res
                    purchases.append(sale)
            if purchases and isinstance(purchases, list):
                self.env['account.move.recv'].sudo().create(purchases)


class AccountMoveLineRecv(models.Model):
    _name = 'account.move.line.recv'
    _description = 'Received Account Move Lines'

    move_id = fields.Many2one('account.move.recv', required=True, ondelete="cascade")
    name = fields.Char(compute='compute_name', store=True)
    company_id = fields.Many2one(related='move_id.company_id', store=True, readonly=True)

    itemSeq = fields.Char('Item Sequence Number', copy=False)
    itemClsCd = fields.Char('Item Classification Code')
    itemCd = fields.Char('Item Code')
    itemNm = fields.Char('Item Name')
    bcd = fields.Char('Barcode')
    pkgUnitCd = fields.Char('Packaging Unit Code')
    pkg = fields.Integer('Package')
    qtyUnitCd = fields.Char('Quantity Unit Code')
    qty = fields.Integer('Quantity')
    prc = fields.Float('Unit Price')
    splyAmt = fields.Float('Supply Amount')
    dcRt = fields.Float('Discount Rate')
    dcAmt = fields.Float('Discount Amount')
    taxTyCd = fields.Char('Taxation Type Code')
    taxblAmt = fields.Float('Taxable Amount')
    taxAmt = fields.Float('Tax Amount')
    totAmt = fields.Float('Total Amount')

    # @api.model
    # def action_fetch_purchaseitems(self):
    #     # TODO: Fetching for a specific purchase
    #     data = {'ids': self.env['account.move.line.recv'].sudo().search([]).mapped('sdc_rec_id')}
    #     res = Messenger(self.env.user, data).recv_purchaseitem()
    #     if res and type(res) == dict:
    #         items = res.get('items')
    #         if items and type(items) == list:
    #             inv_ids = [item['refId'] for item in items]
    #             purchases = self.env['account.move.recv'].sudo().search([('refId', 'in', inv_ids)])
    #             purchases_lookup = {purchase.refId: purchase.id for purchase in purchases}
    #             filtered_items = [{**item, **{'move_id': purchases_lookup[item['refId']]}} for item in items if
    #                               item['refId'] in purchases_lookup]
    #             self.env['account.move.line.recv'].sudo().create(filtered_items)

    @api.depends('itemCd', 'itemNm')
    def compute_name(self):
        for rec in self:
            if rec.itemCd and rec.itemNm:
                rec.name = '[%s]%s' % (rec.itemNm, rec.itemNm)
            else:
                rec.name = rec.itemCd or rec.itemNm or ""


class ImportItem(models.Model):
    _name = 'recv.import.item'

    name = fields.Char(compute='compute_rec_name', store=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True)
    # sdc_rec_id = fields.Integer()
    # operationCd = fields.Char('Operation Code')

    taskCd = fields.Char('Task Code')
    dclDe = fields.Char('Declaration Date')
    itemSeq = fields.Char("Item Sequence")
    dclNo = fields.Char('Declaration Number')
    hsCd = fields.Char("HS Code")
    itemNm = fields.Char("Item Name")
    orgnNatCd = fields.Char("Origin Code")
    exptNatCd = fields.Char("Export Country Code")
    pkg = fields.Char("Packaging Quantity")
    pkgUnitCd = fields.Char("Package Unit Code")
    qty = fields.Char("Quantity")
    qtyUnitCd = fields.Char("Quantity Unit Code")
    totWt = fields.Char("Gross Weight")
    netWt = fields.Char("Net Weight")
    spplrNm = fields.Char("Supplier Name")
    agntNm = fields.Char('Agent Name')
    invcFcurAmt = fields.Char("Invoice Amount in Foreign Currency")
    invcFcurCd = fields.Char("Invoice Currency")
    invcFcurExcrt = fields.Char("Exchange Rate")
    imptItemsttsCd = fields.Char("Status Code")

    send_import_item = fields.Binary(compute='compute_send_import_item')
    state = fields.Selection([('waiting', 'Wait for Approval'), ('approved', 'Approved'), ('rejected', 'Rejected')],
                             default='waiting', string="Status")
    sent_to_vsdc = fields.Boolean(default=False)
    move_line_ids = fields.One2many('account.move.line', 'import_item_id')
    import_request = fields.Html('Request')
    import_response = fields.Html()
    update_request = fields.Html('Request')
    update_response = fields.Html()

    def write(self, vals):
        res = super(ImportItem, self).write(vals)
        if 'state' in vals:
            self.sdc_send_import_item()
        return res

    def unlink(self):
        for rec in self:
            rec.state = 'rejected'
        return super(ImportItem, self).unlink()

    @api.depends('taskCd', 'itemNm')
    def compute_rec_name(self):
        for item in self:
            item.name = f'{item.taskCd} {item.itemNm}'

    def compute_send_import_item(self):
        for item in self:
            send_import_item = Miner().get_import_item_data(item)
            item.send_import_item = send_import_item

    def action_approve(self):
        self.filtered(lambda item: item.state == 'waiting').sudo().write({'state': 'approved'})

    def action_reject(self):
        self.filtered(lambda item: item.state == 'waiting').sudo().write({'state': 'rejected'})

    @api.model
    def action_fetch_items(self):
        cookies = request.httprequest.cookies
        company_id = self.env['res.company'].sudo()
        cid = False
        if cookies.get('cids'):
            cid = cookies.get('cids').split(',')[0]
            if cid:
                company_id = self.env['res.company'].sudo().search([('id', '=', cid)])
        if not company_id.branch_type == 'hq':
            return False
        req_data = {"tin": company_id.vat, "bhfId": company_id.vsdc_branch_id.branch_id, "lastReqDt": company_id.last_request_date}
        res = Messenger(self.env.user, req_data, company=self.env.company, endpoint="imports/selectImportItems").recv_import_item()
        if isinstance(res, dict) and res.get('resultCd') == "000":
            data = res.get('data', {})
            item_list = data.get('itemList', [])
            if item_list:
                for item in item_list:
                    item_exists = self.search([('taskCd', '=', item.get('taskCd', ''))])
                    if not item_exists:
                        if item.get('imptItemsttsCd', '') == '2':
                            item['state'] = 'waiting'
                        if item.get('imptItemsttsCd', '') == '3':
                            item['state'] = 'approved'
                        if item.get('imptItemsttsCd', '') == '4':
                            item['state'] = 'rejected'
                        # item['state'] = 'waiting'
                        item['company_id'] = cid
                        item['import_request'] = req_data
                        item['import_response'] = res
                self.env['recv.import.item'].sudo().create(item_list)
        return {}

    def sdc_send_import_item(self):
        # pass
        _logger.info("Executing sdc_send_import_item...")
        if self.state not in ['approved', 'rejected'] or self.sent_to_vsdc:
            return
        try:
            cookies = request.httprequest.cookies
            company_id = self.env['res.company'].sudo()
            cid = False
            if cookies.get('cids'):
                cid = cookies.get('cids').split(',')[0]
                if cid:
                    company_id = self.env['res.company'].sudo().search([('id', '=', cid)])
            if not company_id.branch_type == 'hq':
                return False

            dt = fields.Datetime.now()
            data = self.send_import_itemdata
            for line in self.move_line_ids:
                if line.move_id:
                    line.move_id.send_import_item = data
            print("data", data)
            self.update_request = data
            res = Messenger(self.env.user, data, company=company_id, endpoint="imports/updateImportItems").send_import_item()
            self.update_response = res
            for line in self.move_line_ids:
                if line.move_id:
                    line.move_id.send_import_response = res
                    line.move_id.synced_date = fields.Datetime.now()
                    line.move_id.message_post(body="Bill successfully synced with VSDC")
            self.env['sdc.log'].get_or_create(company_id, 'send_import_item', res, dt)
            if isinstance(res, dict) and res.get('resultCd') == "000":
                self.write({'sent_to_vsdc': True})
            else:
                # self.message_post(body=f"Sync Response\n: {res}")
                raise ValidationError(f"VSDC Response: {res}")
        except Exception as e:
            _logger.error(_(f"{e}"))

    @api.model
    def cron_send_to_vsdc(self):
        pass
        # self.sdc_send_import_item()
