# -*- coding: utf-8 -*-

from odoo import api, fields, models


class VSDCBranch(models.Model):
    _name = "vsdc.branch"
    _description = "VSDC branch"
    _rec_name = 'branch_name'

    branch_tin = fields.Char(string="Branch TIN")
    branch_id = fields.Char(string="Branch ID")
    branch_name = fields.Char(string="Branch Name")
    branch_status = fields.Selection([('open', 'Open'), ('closed', 'Closed')], string="Branch Status")
    branch_province = fields.Char(string="Branch Province")
    branch_district = fields.Char(string="Branch District")
    branch_sector = fields.Char(string="Branch Sector")
    branch_location = fields.Char(string="Branch Location Description")
    branch_type = fields.Selection([('hq', 'Head Quarter'), ('br', 'Branch')], string="Branch Type")

    branch_manager_name = fields.Char(string="Branch Manager Name")
    branch_manager_phone = fields.Char(string="Branch Manager Tel")
    branch_manager_email = fields.Char(string="Branch Manager Email")

    def name_get(self):
        result = []
        for branch in self:
            result.append((branch.id, "%s (%s)" % (branch.branch_name, branch.branch_id)))
        return result


class VSDCReturnReason(models.Model):
    _name = 'vsdc.return.reason'
    _description = 'Return Reason'

    code = fields.Char(string="Code")
    name = fields.Char(string="Name")
    description = fields.Char(string="Description")
    active = fields.Boolean(string="Active")
    user_defined_code1 = fields.Char(string="User Defined Code 01")
    user_defined_code2 = fields.Char(string="User Defined Code 02")
    user_defined_code3 = fields.Char(string="User Defined Code 03")


class VSDCPaymentMethod(models.Model):
    _name = 'vsdc.payment.method'
    _description = 'VSDC Payment Methods'

    code = fields.Char(string="Code")
    name = fields.Char(string="Name")
    description = fields.Char(string="Description")
    active = fields.Boolean(string="Active")
    user_defined_code1 = fields.Char(string="User Defined Code 01")
    user_defined_code2 = fields.Char(string="User Defined Code 02")
    user_defined_code3 = fields.Char(string="User Defined Code 03")


class VSDCInventoryAdjustmentReason(models.Model):
    _name = 'vsdc.inventory.adjustment.reason'
    _description = 'Inventory Adjustment Reason'

    code = fields.Char(string="Code")
    name = fields.Char(string="Name")
    description = fields.Char(string="Description")
    active = fields.Boolean(string="Active")
    user_defined_code1 = fields.Char(string="User Defined Code 01")
    user_defined_code2 = fields.Char(string="User Defined Code 02")
    user_defined_code3 = fields.Char(string="User Defined Code 03")


class VSDCStockInOutTypes(models.Model):
    _name = 'vsdc.stock.in.out.type'
    _description = 'Stock In/Out Type'

    code = fields.Char(string="Code")
    name = fields.Char(string="Name")
    description = fields.Char(string="Description")
    active = fields.Boolean(string="Active")
    user_defined_code1 = fields.Char(string="User Defined Code 01")
    user_defined_code2 = fields.Char(string="User Defined Code 02")
    user_defined_code3 = fields.Char(string="User Defined Code 03")
