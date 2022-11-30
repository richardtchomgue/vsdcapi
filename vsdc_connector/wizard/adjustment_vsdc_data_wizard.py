from odoo import api, fields, models


class VSDCAdjustmentWizard(models.TransientModel):
    _name = 'vsdc.adjustment.wizard'
    _description = 'Inventory Adjustment Data Wizard'

    is_synced = fields.Text('Synced')
    synced_date = fields.Text('Synced Date')
    date_sent = fields.Text('Data Sent')
    response = fields.Text('Response')

    def action_ok(self):
        """ close wizard"""
        return {'type': 'ir.actions.act_window_close'}
