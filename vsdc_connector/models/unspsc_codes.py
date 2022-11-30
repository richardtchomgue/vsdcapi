from odoo import api, fields, models


class ItemClassificationCode(models.Model):
    _name = 'item.classification'
    _description = 'Item Classification'
    _rec_name = 'rec_name'
    _order = 'code asc'

    rec_name = fields.Char(compute='compute_rec_name', store=True)
    code = fields.Char('Item Classification Code')
    name = fields.Char('Item Classification Name')
    level = fields.Integer(default=1, string="Item Classification Level")
    rra_code = fields.Selection([('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')], string="RRA code")

    @api.depends('code', 'name')
    def compute_rec_name(self):
        for rec in self:
            rec.rec_name = f"{rec.code} {rec.name}"
