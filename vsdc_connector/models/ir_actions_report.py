from odoo import models, _
from odoo.exceptions import UserError


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, res_ids=None, data=None):
        # Overridden so that the print > invoices actions raises an error
        # when trying to print an invoice without RRA stamp
        moves = None
        if self.model == 'account.move' and res_ids:
            invoice_reports = (
                self.env.ref('account.account_invoices_without_payment'), self.env.ref('account.account_invoices'))
            if self in invoice_reports:
                moves = self.env['account.move'].browse(res_ids)
                if any(move.state == 'posted' and move.invoice_ok and not move.stamps for move in moves):
                    raise UserError(_("Cannot print an invoice without RRA stamp. Try sending the invoice(s) to VSDC "
                                      "and then try again"))

        res = super()._render_qweb_pdf(res_ids=res_ids, data=data)
        if moves:
            moves.filtered(lambda move: move.invoice_ok).mark_printed()
        return res
