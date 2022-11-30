import logging
import pytz

from odoo import models, fields, _, api
from odoo.tools import float_compare
from odoo.addons.vsdc_connector.controllers.api_calls import Messenger
from odoo.exceptions import UserError, ValidationError

from .utils import _special

tz = pytz.timezone("Africa/Kigali")

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    adjustment_note = fields.Text('Adjustment Note')
    is_synced = fields.Boolean('Synced')
    synced_date = fields.Datetime('Synced Date')
    date_sent = fields.Text('Data Sent')
    response = fields.Text('Response')

    @api.model
    def _get_inventory_fields_create(self):
        """ Returns a list of fields user can edit when he want to create a quant in `inventory_mode`.
        """
        res = super()._get_inventory_fields_create()
        res += ['adjustment_note']
        res += ['is_synced']
        return res

    def action_view_vsdc_data(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _("VSDC Data"),
            'res_model': 'vsdc.adjustment.wizard',
            'view_mode': 'form',
            'context': {'default_is_synced': self.is_synced,
                        'default_synced_date': self.synced_date,
                        'default_date_sent': self.date_sent,
                        'default_response': self.response,
                        },
            "target": "new",
        }

    def get_inventory_adjustment_lines(self):
        def _compute_tax(lyne):
            lyne_prc = lyne.product_id.list_price
            lyne_tax_ids = lyne.product_id.taxes_id
            computed = lyne_tax_ids.compute_all(price_unit=lyne_prc,
                                                currency=self.env.company.currency_id,
                                                quantity=lyne.quantity,
                                                product=lyne.product_id)
            tax_amt = sum(t.get('amount', 0.0) for t in computed.get('taxes', []))
            total_included = computed["total_included"]

            return {'tax_amt': tax_amt, 'price_total': total_included}

        items = []
        for index, line in enumerate(self):

            msg = ''
            if not line.product_id.item_code:
                msg = "Define Product Code on product."
            if not line.product_id.unspsc_categ_id.code:
                msg += 'Define UNSPSC Category Code on product.'
            if not line.product_id.quantity_unit.code:
                msg += 'Define Unit of Quantity on product.'
            if not line.product_id.packaging_unit.code:
                msg += 'Define Packaging Unit on product.'

            if not line.product_id.item_code or not line.product_id.unspsc_categ_id.code \
                    or not line.product_id.packaging_unit.code or not line.product_id.quantity_unit.code:
                raise ValidationError(f"Product Attribute Missing: {msg}")

            prc = line.product_id.list_price
            discount = 0
            tax_ids = line.product_id.taxes_id

            price_total = _compute_tax(line).get('price_total', 0)

            line_data = {
                "itemSeq": index,
                "itemCd": line.product_id.item_code,
                "itemClsCd": line.product_id.unspsc_categ_id.code,
                "itemNm": line.product_id.name,
                "bcd": line.product_id.barcode or None,
                "pkgUnitCd": line.product_id.packaging_unit.code,
                "pkg": line.quantity,  # TODO
                "qtyUnitCd": line.product_id.quantity_unit.code,
                "qty": line.quantity,
                "itemExprDt": None,
                "prc": prc,
                "splyAmt": prc * line.quantity,
                "totDcAmt": discount,
                "taxblAmt": price_total,
                "taxTyCd": (tax_ids and tax_ids[0].rra_code) or "B",
                "taxAmt": _special(_compute_tax(line).get('tax_amt', 0)),
                "totAmt": price_total,
            }
            items.append(line_data)

        return items

    def update_vsdc_stock(self):
        for quant in self:
            remark = None
            if quant.adjustment_note:
                remark = quant.adjustment_note
            sar_no = quant.location_id.warehouse_id.id if quant.location_id.warehouse_id else quant.location_id.id
            sar_type = '06'

            quant_date = quant.inventory_date.strftime('%Y%m%d') if quant.inventory_date else None

            items = quant.get_inventory_adjustment_lines()

            amount_total = sum([i.get('totAmt') for i in items])
            amount_tax = sum([float(j.get('taxAmt')) for j in items])

            data = {
                "tin": quant.company_id.vat,
                "bhfId": quant.company_id.branch_id,
                "sarNo": sar_no,
                "orgSarNo": sar_no,
                "regTyCd": "M",  # TODO
                "custTin": None,
                "custNm": None,
                "custBhfId": None,  # TODO
                "sarTyCd": sar_type,
                "ocrnDt": quant_date,
                "totItemCnt": len(items),
                "totTaxblAmt": amount_total,
                "totTaxAmt": amount_tax,
                "totAmt": amount_total,
                "remark": remark,
                "regrId": self.env.user.name,
                "regrNm": self.env.user.name,
                "modrNm": self.env.user.name,
                "modrId": self.env.user.name,
                "itemList": items,
            }

            try:
                quant.date_sent = data
                if not quant.company_id.sdc_base_url:
                    raise UserError(_(f"VSDC Base URL is not configured for {quant.company_id.name}"))
                dt = fields.Datetime.now()
                res = Messenger(self.env.user, data, company=quant.company_id,
                                endpoint='stock/saveStockItems').send_inventory()
                quant.response = res
                self.env['sdc.log'].get_or_create(quant.company_id, 'send_inventory', res, dt)
                if res.get('resultCd') == "000":
                    quant.is_synced = True
                    quant.synced_date = fields.Datetime.now()

            except Exception as e:
                _logger.error(f"{e}")

    @api.model
    def _update_available_quantity(self, product_id, location_id, quantity, lot_id=None, package_id=None, owner_id=None,
                                   in_date=None):
        """
        Override to ensure that the quantity is never set to negative
        If the resulting value is negative, we change it to the absolute equivalent then auto adjust it to zero
        """
        self = self.sudo()
        quants = self._gather(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id,
                              strict=True)

        if location_id.should_bypass_reservation():
            incoming_dates = []
        else:
            incoming_dates = [quant.in_date for quant in quants if quant.in_date and
                              float_compare(quant.quantity, 0, precision_rounding=quant.product_uom_id.rounding) > 0]
        if in_date:
            incoming_dates += [in_date]
        # If multiple incoming dates are available for a given lot_id/package_id/owner_id, we
        # consider only the oldest one as being relevant.
        if incoming_dates:
            in_date = min(incoming_dates)
        else:
            in_date = fields.Datetime.now()

        quant = None
        if quants:
            # see _acquire_one_job for explanations
            self._cr.execute("SELECT id FROM stock_quant WHERE id IN %s LIMIT 1 FOR NO KEY UPDATE SKIP LOCKED",
                             [tuple(quants.ids)])
            stock_quant_result = self._cr.fetchone()
            if stock_quant_result:
                quant = self.browse(stock_quant_result[0])

        if quant:
            cuml_qty = quant.quantity + quantity
            quant.write({
                'quantity': abs(cuml_qty),
                'in_date': in_date,
            })
        else:
            # Always create the quant with a positive value then auto adjust to 0 if the passed value was negative
            cuml_qty = quantity
            quant = self.create({
                'product_id': product_id.id,
                'location_id': location_id.id,
                'quantity': abs(quantity),
                'lot_id': lot_id and lot_id.id,
                'package_id': package_id and package_id.id,
                'owner_id': owner_id and owner_id.id,
                'in_date': in_date,
            })
        if cuml_qty < 0:
            quant.inventory_quantity = 0
            quant.action_apply_inventory()
        res = self._get_available_quantity(product_id, location_id, lot_id=lot_id, package_id=package_id,
                                           owner_id=owner_id, strict=False, allow_negative=True), in_date
        return res

    @api.model
    def pos_check_quantity(self, session_id, quantities):
        quantities = {int(k): int(val) for k, val in quantities.items()}
        _logger.info("Demanded Quantities: {}".format(quantities))
        session = self.env['pos.session'].sudo().browse(session_id)
        location = session.config_id.picking_type_id.default_location_src_id
        _logger.info("Session: {}, Location: {}".format(session.name, location.complete_name))
        product_ids = list(quantities.keys())
        products = {product.id: product.name for product in self.env['product.product'].browse(product_ids)}
        quants = self.env['stock.quant'].sudo().search(
            ['|', ('location_id', '=', location.id), ('location_id', 'child_of', location.id),
             ('product_id', 'in', product_ids)])
        available = {quant.product_id.id: quant.quantity for quant in quants}
        _logger.info("Available quantities: {}".format(available))
        res = [[product_id, qty, available[product_id] if product_id in available else 0] for product_id, qty in
               quantities.items()]
        return {'location': location.complete_name,
                'lines': [[products[product_id], qty, available] for product_id, qty, available in res if
                          qty > available]}

    def _apply_inventory(self):
        res = super(StockQuant, self)._apply_inventory()
        adjustment_note = ""
        if any(q.adjustment_note for q in self):
            adjustment_note = self[0].adjustment_note
        for quant in self:
            if not quant.adjustment_note:
                quant.adjustment_note = adjustment_note
        self.update_vsdc_stock()

        return res
