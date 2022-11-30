from odoo import api, fields, models


class QuantityUnit(models.Model):
    _name = 'quantity.unit'
    _description = 'Quantity Unit'

    code = fields.Char(required=True)
    name = fields.Char(required=True)
    description = fields.Char()


class PackagingUnit(models.Model):
    _name = 'packaging.unit'
    _description = 'Quantity Unit'

    code = fields.Char(required=True)
    name = fields.Char(required=True)
    description = fields.Char()