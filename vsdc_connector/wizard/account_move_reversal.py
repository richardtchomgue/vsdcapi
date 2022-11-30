# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools.translate import _
from odoo.exceptions import UserError


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    reason_id = fields.Many2one('vsdc.return.reason', string="Select Reason")
    reason = fields.Char(related='reason_id.name', string="Reason")

    def reverse_moves(self):
        """Always cancel the original invoice"""
        self.refund_method = 'cancel'
        return super(AccountMoveReversal, self).reverse_moves()

    def _prepare_default_reversal(self, move):
        default_vals = super(AccountMoveReversal, self)._prepare_default_reversal(move)
        default_vals.update({'reason_id': self.reason_id.id})
        return default_vals