from odoo import models, api


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @staticmethod
    def force_to_invoice(order):
        order['data'].update({'to_invoice': True})
        order.update({'to_invoice': True})
        return order

    @api.model
    def create_from_ui(self, orders, draft=False):
        orders = [self.force_to_invoice(order) for order in orders]
        return super(PosOrder, self).create_from_ui(orders, draft=draft)

    def _export_for_ui(self, order):
        res = super(PosOrder, self)._export_for_ui(order)
        _reversed = order.account_move and order.account_move.reversal_move_id
        res.update({'reversed': bool(_reversed)})
        return res
