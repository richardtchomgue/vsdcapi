from odoo import models, api, fields, _
from odoo.exceptions import UserError

from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    payment_method_id = fields.Many2one('pos.payment.method', string="Payment Method")

    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        invoice_vals['payment_method_id'] = self.payment_method_id.id
        return invoice_vals

    @api.onchange('payment_method_id')
    def onchange_payment_method_id(self):
        vsdc_payment = self.payment_method_id.vsdc_payment_method_id
        if self.payment_method_id and not vsdc_payment:
            raise ValidationError("Please link the VSDC Payment Method with this payment Method!")


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _compute_tax_id(self):
        for line in self:
            company = line.order_id.company_id
            fpos = line.order_id.fiscal_position_id or line.order_id.partner_id.property_account_position_id
            # If company_id is set in the order, always filter taxes by the company
            taxes = line.product_id.taxes_id.filtered(lambda r: r.company_id == company)

            line.tax_id = fpos.map_tax(taxes, line.product_id, line.order_id.partner_shipping_id) if fpos else taxes

            if not line.tax_id and company.account_sale_tax_id and line.product_id.type != 'service':
                line.tax_id = company.account_sale_tax_id

    @api.constrains('price_unit', 'product_uom_qty')
    def zero_price_constraint(self):
        for line in self:
            if not (line.price_unit > 0 and line.product_uom_qty > 0):
                raise UserError(_(f'Invalid quantity or price on line {line.name}'))
