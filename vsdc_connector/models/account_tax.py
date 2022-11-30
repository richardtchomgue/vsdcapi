import math

from odoo import models, fields, _, api
from odoo.exceptions import UserError


class AccountTax(models.Model):
    _inherit = 'account.tax'
    _order = 'rra_code'

    rra_code = fields.Selection([('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')], string="RRA code", default="B",
                                required=True)
    price_include = fields.Boolean(string='Included in Price', default=True, readonly=True,
                                   help="Check this if the price you use on the product and invoices includes this tax.")
    include_base_amount = fields.Boolean(string='Affect Base of Subsequent Taxes', default=False, readonly=True,
                                         help="If set, taxes which are computed after this one will be computed based on the price tax included.")

    label = fields.Char(string="Tax Label", compute="compute_label")

    def write(self, values):
        values.update({'price_include': True, 'include_base_amount': False})
        return super(AccountTax, self).write(values)

    def rounded_rate(self, rate):
        return rate.is_integer and int(rate) or rate

    @api.depends('rra_code', 'amount')
    def compute_label(self):
        for tax in self:
            if tax.rra_code == 'A':
                label = 'A-EX'
            elif tax.rra_code == 'B':
                label = f'B-{self.rounded_rate(tax.amount)}%'
            else:
                label = tax.rra_code
            tax.label = label


class AccountTaxTemplate(models.Model):
    _inherit = 'account.tax.template'

    price_include = fields.Boolean(string='Included in Price', default=True, readonly=True,
                                   help="Check this if the price you use on the product and invoices includes this tax.")
    include_base_amount = fields.Boolean(string='Affect Base of Subsequent Taxes', default=False, readonly=True,
                                         help="If set, taxes which are computed after this one will be computed based on the price tax included.")