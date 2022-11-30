from odoo import api, fields, models, _


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    vsdc_payment_method_id = fields.Many2one('vsdc.payment.method', string="VSDC Payment Method")
