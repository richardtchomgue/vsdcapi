from odoo import models, api, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.constrains('partner_id')
    def check_vat_country(self):
        partners = self.mapped('partner_id')
        partner = next((partner for partner in partners if not (partner.vat and partner.country_id)), None)
        if partner:
            if not partner.vat:
                raise UserError(_(f"Please set the VAT number for {partner.name}"))
            elif not partner.country_id:
                raise UserError(_(f"Please set the country for {partner.name}"))


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _compute_tax_id(self):
        for line in self:
            company = line.order_id.company_id
            fpos = line.order_id.fiscal_position_id or line.order_id.partner_id.with_context(
                force_company=line.company_id.id).property_account_position_id
            # If company_id is set in the order, always filter taxes by the company
            taxes = line.product_id.supplier_taxes_id.filtered(lambda r: r.company_id == company)
            line.taxes_id = fpos.map_tax(taxes, line.product_id, line.order_id.partner_id) if fpos else taxes

            if not line.taxes_id and company.account_purchase_tax_id and line.product_id.type != 'service':
                line.taxes_id = company.account_purchase_tax_id

    @api.constrains('price_unit', 'product_uom_qty')
    def zero_price_constraint(self):
        for line in self:
            if not (line.price_unit > 0 and line.product_uom_qty > 0):
                raise UserError(_(f'Invalid quantity or price on line {line.name}'))
