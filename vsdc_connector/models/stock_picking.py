# -*- coding: utf-8 -*-

import logging
import pytz

from odoo import models, fields, _, api
from odoo.addons.vsdc_connector.controllers.api_calls import Messenger
from odoo.exceptions import UserError, ValidationError

from .utils import Miner

tz = pytz.timezone("Africa/Kigali")

_logger = logging.getLogger(__name__)


class ReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    def _prepare_picking_default_values(self):
        vals = super(ReturnPicking, self)._prepare_picking_default_values()
        if self.picking_id.purchase_id:
            vals.update({'is_purchase_refund': True})
        if self.picking_id.pos_order_id or self.sale_id:
            vals.update({'is_sale_refund': True})
        return vals


class Picking(models.Model):
    _inherit = "stock.picking"

    is_sale_refund = fields.Boolean()
    is_purchase_refund = fields.Boolean()
    sent_to_vsdc = fields.Boolean(default=False)
    synced_date = fields.Datetime(help="The date at which the data is synced with VSDC", string="Synced with VSDC at")
    date_sent = fields.Text()
    response = fields.Text()
    stock_in_out_id = fields.Many2one('vsdc.stock.in.out.type', string="Stock In/Out Type")

    def _action_done(self):
        res = super(Picking, self)._action_done()
        self.update_vsdc_stock()
        return res

    def update_vsdc_stock(self):
        for picking in self:
            item_inventory_data = Miner().get_inventory_data(picking)
            self.date_sent = item_inventory_data
            try:
                if not picking.company_id.sdc_base_url:
                    raise UserError(_(f"VSDC Base URL is not configured for {picking.company_id.name}"))
                dt = fields.Datetime.now()
                res = Messenger(picking.create_uid, item_inventory_data, company=picking.company_id, endpoint='stock/saveStockItems').send_inventory()
                self.response = res
                self.env['sdc.log'].get_or_create(picking.company_id, 'send_inventory', res, dt)
                if res.get('resultCd') == "000":
                    picking.sent_to_vsdc = True
                    picking.synced_date = fields.Datetime.now()
                    picking.message_post(body="Stock Updated in VSDC")
                else:
                    picking.message_post(body=f"Inventory Sync Failed!\n See detailed response: {res}")
            except Exception as e:
                picking.message_post(body=f"Inventory Sync Failed!\n See detailed response: {e}")
                _logger.error(f"{e}")

    def _prepare_stock_move_vals(self, first_line, order_lines):
        res = super(Picking, self)._prepare_stock_move_vals(first_line=first_line, order_lines=order_lines)
        res.update({
            'prc': abs(sum(order_lines.mapped('price_unit'))),
            'price_total': abs(sum(order_lines.mapped('price_subtotal_incl'))),
            'discount': abs(sum(order_lines.mapped('discount'))),
            'tax_id': order_lines.mapped('tax_ids_after_fiscal_position') or order_lines.mapped('tax_ids')
        })
        return res


class StockMove(models.Model):
    _inherit = "stock.move"

    prc = fields.Integer()
    price_total = fields.Integer()
    discount = fields.Integer()
    tax_id = fields.Many2many('account.tax', string='Taxes')
