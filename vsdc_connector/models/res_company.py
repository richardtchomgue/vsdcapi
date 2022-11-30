import json
from pprint import pprint
import requests
import logging

from odoo import models, fields, api, _

from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    # VSDC Auth Details
    default_customer = fields.Many2one('res.partner', 'Default Customer')
    sdc_base_url = fields.Char(string='SDC Base URL')
    sdc_serial_no = fields.Char(string='SDC Customer Serial Number')
    device_installed = fields.Boolean(string='Is Installed?')
    last_request_date = fields.Char(string='Last Request Date')

    essentials_request = fields.Html(string='Essentials Request')
    essentials = fields.Html(string='Essentials Response')
    item_class_request = fields.Html(string='Item Classification Request')
    item_class = fields.Html(string='Item Classification')

    initialize_request = fields.Html(string='Initialize Request')
    initialize_response = fields.Html(string='Initialize Response')

    ist_initialize_request = fields.Html(string='Initial Initialize Request')
    ist_initialize_response = fields.Html(string='Initial Initialize Response')

    initialized = fields.Boolean(string='Initialized?')

    import_branches_request = fields.Html(string='Import Branch Request')
    import_branches_response = fields.Html(string='Import Branch Response')

    # Tax Payer Information
    company_name = fields.Char(string='Company Name')
    business_Activity = fields.Char(string='Business Activity')
    branch_id = fields.Char(string="SDC Branch ID")
    branch_office_name = fields.Char(string="Branch Office Name")
    branch_date_created = fields.Char(string="Branch Date Created")

    # Tax Payer Address Information
    province_name = fields.Char(string="Province Name")
    district_name = fields.Char(string="District Name")
    sector_name = fields.Char(string="Sector Name")
    location = fields.Char(string="Location")

    # Management Details
    manager_name = fields.Char(string="Manager Name")
    manager_phone = fields.Char(string="Manager Phone Number")
    manager_email = fields.Char(string="Manager Email")

    # VSDC Information
    sdc_id = fields.Char(string="SDC ID")
    mrc_number = fields.Char(string="MRC No")
    device_id = fields.Char(string="Device ID")
    internal_key = fields.Char(string="Internal Key")
    sign_key = fields.Char(string="Sign Key")
    communication_key = fields.Char(string="Communication Key")

    # VSDC Courier
    last_sale_invoice_number = fields.Char(string="Last Sale Invoice No")
    last_purchase_invoice_number = fields.Char(string="Last Purchase Invoice No")
    last_invoice_number = fields.Char(string="Last Invoice No")
    last_sale_receipt_number = fields.Char(string="Last Sale Receipt No")
    last_cis_invoice_number = fields.Char(string="Last CIS Invoice No")
    last_training_invoice_number = fields.Char(string="Last Training Invoice No")
    last_proforma_invoice_number = fields.Char(string="Last Proforma Invoice No")
    last_copy_invoice_number = fields.Char(string="Last Copy Invoice No")

    # Branch Details
    vsdc_branch_id = fields.Many2one('vsdc.branch', string="Branch")
    branch_tin = fields.Char(related="vsdc_branch_id.branch_tin")
    branch = fields.Char(related="vsdc_branch_id.branch_id")
    branch_name = fields.Char(related="vsdc_branch_id.branch_name")
    branch_status = fields.Selection(related="vsdc_branch_id.branch_status")
    branch_province = fields.Char(related="vsdc_branch_id.branch_province")
    branch_district = fields.Char(related="vsdc_branch_id.branch_district")
    branch_sector = fields.Char(related="vsdc_branch_id.branch_sector")
    branch_location = fields.Char(related="vsdc_branch_id.branch_location")
    branch_type = fields.Selection(related="vsdc_branch_id.branch_type")
    branch_manager_name = fields.Char(related="vsdc_branch_id.branch_manager_name")
    branch_manager_phone = fields.Char(related="vsdc_branch_id.branch_manager_phone")
    branch_manager_email = fields.Char(related="vsdc_branch_id.branch_manager_email")

    # def write(self, values):
    #     if 'vat' in values and values['vat'] != self.vat:
    #         if self.env['account.move'].sudo().search(
    #                 [('state', '!=', 'draft'), ('company_id', '=', self.id)]).exists():
    #             raise UserError(_("You can't change the Tax ID for a company with posted journal entries"))
    #     return super(ResCompany, self).write(values)

    def show_message(self, message):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Device Status"),
            'res_model': 'feedback.wizard',
            'view_mode': 'form',
            'context': {'default_message': message},
            "target": "new",
        }

    def action_check_pass(self):
        pass

    def action_update_company_details(self):
        currency_id = self.env['res.currency'].sudo().search([('name', '=', 'RWF')])
        self.name = self.branch_name
        self.street2 = f"{self.branch_district}, {self.branch_sector}"
        self.city = self.branch_province
        self.vat = self.branch_tin
        self.currency_id = currency_id.id or False

    def action_import_vsdc_branches(self):
        """Import VSDC Branches"""
        if not self.sdc_base_url or not self.vat or not self.branch_id or not self.last_request_date:
            raise ValidationError("Please provide the auth details for VSDC!")
        headers = {"Content-Type": 'application/json'}
        data = json.dumps({"tin": self.vat, "bhfId": self.branch_id, "lastReqDt": self.last_request_date})
        url = f"{self.sdc_base_url}/branches/selectBranches"
        try:
            response = requests.post(url, data=data, headers=headers, verify=False)
            if response.status_code == 200:
                pprint(response.json())
                json_response = response.json()
                self.import_branches_response = json_response
                if json_response.get('resultCd', '') == '000':
                    json_data = json_response.get('data', {})
                    json_branch_list = json_data.get('bhfList', [])
                    branches_list = []
                    existing_branch_ids = self.env['vsdc.branch'].sudo().search([])
                    for branch in json_branch_list:
                        if not existing_branch_ids.filtered(
                                lambda b: b.branch_name == branch.get('bhfNm', '') and b.branch_id == branch.get(
                                    'bhfId', '')):
                            branches_list.append({
                                'branch_tin': branch.get('tin', ''),
                                'branch_id': branch.get('bhfId', ''),
                                'branch_name': branch.get('bhfNm', ''),
                                'branch_status': 'open' if branch.get('bhfSttsCd', '') == '01' else 'closed',
                                'branch_province': branch.get('prvncNm', ''),
                                'branch_district': branch.get('dstrtNm', ''),
                                'branch_sector': branch.get('sctrNm', ''),
                                'branch_location': branch.get('locDesc', ''),
                                'branch_type': 'hq' if branch.get('hqYn', '') == 'Y' else 'br',

                                'branch_manager_name': branch.get('mgrNm', ''),
                                'branch_manager_phone': branch.get('mgrTelNo', ''),
                                'branch_manager_email': branch.get('mgrEmail', ''),
                            })
                    branches_ids = self.env['vsdc.branch'].sudo().create(branches_list)
                    branches_count = len(branches_ids)
                    _logger.info(f'########################## [{branches_count}] VSDC Branches Created Successfully.')

                else:
                    raise ValidationError(f"Response: {json_response}")
        except Exception as e:
            raise ValidationError(f"Something went wrong: {e}")

    def action_initialize_vsdc(self):
        """Initialize new VSDC Device"""
        if not self.sdc_base_url or not self.vat or not self.branch_id or not self.sdc_serial_no:
            raise ValidationError("Please provide the auth details for VSDC!")
        headers = {"Content-Type": 'application/json'}
        data = json.dumps({"tin": self.vat, "bhfId": self.branch_id, "dvcSrlNo": self.sdc_serial_no})
        self.initialize_request= data
        if not self.sdc_base_url:
            raise ValidationError("Please provide a base URL!")
        url = f"{self.sdc_base_url}/initializer/selectInitInfo"
        try:
            response = requests.post(url, data=data, headers=headers, verify=False)
            if response.status_code == 200:
                pprint(response.json())
                json_response = response.json()
                self.initialize_response = json_response
                if json_response.get('resultCd', '') == '000':
                    json_data = json_response.get('data', {})
                    json_info = json_data.get('info', {})

                    self.company_name = json_info.get('taxprNm', '')
                    self.business_Activity = json_info.get('bsnsActv', '')
                    self.branch_office_name = json_info.get('bhfNm', '')
                    self.branch_date_created = json_info.get('bhfOpenDt', '')

                    self.province_name = json_info.get('prvncNm', '')
                    self.district_name = json_info.get('dstrtNm', '')
                    self.sector_name = json_info.get('sctrNm', '')
                    self.location = json_info.get('locDesc', '')

                    self.manager_name = json_info.get('mgrNm', '')
                    self.manager_phone = json_info.get('mgrTelNo', '')
                    self.manager_email = json_info.get('mgrEmail', '')

                    self.sdc_id = json_info.get('sdcId', '')
                    self.mrc_number = json_info.get('mrcNo', '')
                    self.device_id = json_info.get('dvcId', '')
                    self.internal_key = json_info.get('intrlKey', '')
                    self.sign_key = json_info.get('signKey', '')
                    self.communication_key = json_info.get('cmcKey', '')

                    self.last_purchase_invoice_number = json_info.get('lastPchsInvcNo', '')
                    self.last_sale_receipt_number = json_info.get('lastSaleRcptNo', '')
                    self.last_invoice_number = json_info.get('lastInvcNo', '')
                    self.last_sale_invoice_number = json_info.get('lastSaleInvcNo', '')
                    self.last_training_invoice_number = json_info.get('lastTrainInvcNo', '')
                    self.last_proforma_invoice_number = json_info.get('lastProfrmInvcNo', '')
                    self.last_copy_invoice_number = json_info.get('lastCopyInvcNo', '')
                    self.ist_initialize_request = response
                    self.ist_initialize_response = data
                    self.initialized = True
                    self.device_installed = True
                elif json_response.get('resultCd', '') == '902':
                    self.initialized = True
                    self.device_installed = True

                return self.show_message(json_response.get('resultMsg', ''))
        except Exception as e:
            raise ValidationError(f"Something went wrong: {e}")

    # def action_check_device_status(self):
    #     """Check device status"""
    #     if not self.sdc_base_url or not self.vat or not self.branch_id or not self.sdc_serial_no:
    #         raise ValidationError("Please provide the auth details for VSDC!")
    #     headers = {"Content-Type": 'application/json'}
    #     data = json.dumps({"tin": self.vat, "bhfId": self.branch_id, "dvcSrlNo": self.sdc_serial_no})
    #     if not self.sdc_base_url:
    #         return
    #     url = f"{self.sdc_base_url}/initializer/selectInitInfo"
    #     try:
    #         response = requests.post(url, data=data, headers=headers, verify=False)
    #         if response.status_code == 200:
    #             pprint(response.json())
    #             json_response = response.json()
    #             if json_response.get('resultCd', '') == '902':
    #                 self.device_installed = True
    #             else:
    #                 self.device_installed = False
    #             return self.show_message(json_response.get('resultMsg', ''))
    #     except Exception as e:
    #         raise ValidationError(f"Something went wrong: {e}")

    def action_import_essentials(self):
        """Import required Essentials from VSDC"""
        if not self.sdc_base_url or not self.vat or not self.branch_id or not self.last_request_date:
            raise ValidationError("Please provide the auth details for VSDC!")
        headers = {"Content-Type": 'application/json'}
        data = json.dumps({"tin": self.vat, "bhfId": self.branch_id, "lastReqDt": self.last_request_date})
        self.essentials_request = data
        url = f"{self.sdc_base_url}/code/selectCodes"
        try:
            response = requests.post(url, data=data, headers=headers, verify=False)
            if response.status_code == 200:
                pprint(response.json())
                json_response = response.json()
                if json_response.get('resultCd', '') == '000':
                    self.essentials = json_response
                    json_data = json_response.get('data', {})
                    json_class_list = json_data.get('clsList', [])
                    if json_class_list:

                        ##########################################
                        ########## Create Taxes in Odoo ##########
                        ##########################################
                        tax_types = next(item for item in json_class_list if item["cdCls"] == "04" and item["dtlList"])
                        tax_list = []
                        TaxSudo = self.env['account.tax'].sudo()
                        for tax_type in tax_types.get('dtlList', []):
                            sale_tax_type_exists = TaxSudo.search([('type_tax_use', '=', 'sale'),
                                                                   ('amount', '=', int(tax_type.get('userDfnCd1', ''))),
                                                                   ('name', '=', f"Tax {tax_type.get('cdNm', '')}")])
                            purchase_tax_type_exists = TaxSudo.search([('type_tax_use', '=', 'purchase'),
                                                                       ('amount', '=',
                                                                        int(tax_type.get('userDfnCd1', ''))),
                                                                       (
                                                                       'name', '=', f"Tax {tax_type.get('cdNm', '')}")])
                            if not sale_tax_type_exists:
                                tax_list.append({
                                    'name': f"Tax {tax_type.get('cdNm', '')}",
                                    'description': f"Tax {tax_type.get('cdNm', '')}",
                                    'type_tax_use': 'sale',
                                    'active': True if tax_type.get('useYn', '') == 'Y' else False,
                                    'amount': int(tax_type.get('userDfnCd1', '')),
                                    'amount_type': 'percent',
                                    'rra_code': tax_type.get('cd', ''),
                                    'company_id': self.id,
                                })
                            if not purchase_tax_type_exists:
                                tax_list.append({
                                    'name': f"Tax {tax_type.get('cdNm', '')}",
                                    'description': f"Tax {tax_type.get('cdNm', '')}",
                                    'type_tax_use': 'purchase',
                                    'active': True if tax_type.get('useYn', '') == 'Y' else False,
                                    'amount': int(tax_type.get('userDfnCd1', '')),
                                    'amount_type': 'percent',
                                    'rra_code': tax_type.get('cd', ''),
                                    'company_id': self.id,
                                })
                        tax_ids = TaxSudo.create(tax_list)
                        taxes_count = len(tax_ids)
                        _logger.info(f'########################## [{taxes_count}] VSDC Taxes Created Successfully')

                        ##########################################
                        ###### Create Product Units in Odoo ######
                        ##########################################
                        quantity_units = next(
                            item for item in json_class_list if item["cdCls"] == "10" and item["dtlList"])
                        quantity_units_list = []
                        QuantityUnitSudo = self.env['quantity.unit'].sudo()
                        for quantity_unit in quantity_units.get('dtlList', []):
                            quantity_unit_exists = QuantityUnitSudo.search([('code', '=', quantity_unit.get('cd', '')),
                                                                            (
                                                                                'name', '=',
                                                                                quantity_unit.get('cdNm', ''))])
                            if not quantity_unit_exists:
                                quantity_units_list.append({
                                    'code': quantity_unit.get('cd', ''),
                                    'name': quantity_unit.get('cdNm', ''),
                                    'description': quantity_unit.get('cdDesc', ''),
                                })
                        quantity_unit_ids = QuantityUnitSudo.create(quantity_units_list)
                        quantity_units_count = len(quantity_unit_ids)
                        _logger.info(
                            f'########################## [{quantity_units_count}] VSDC Product Quantity Units Created Successfully')

                        ##########################################
                        ###### Create Product Units in Odoo ######
                        ##########################################
                        packaging_units = next(
                            item for item in json_class_list if item["cdCls"] == "17" and item["dtlList"])
                        packaging_units_list = []
                        PackageUnitSudo = self.env['packaging.unit'].sudo()
                        for packaging_unit in packaging_units.get('dtlList', []):
                            packaging_unit_exists = PackageUnitSudo.search([('code', '=', packaging_unit.get('cd', '')),
                                                                            ('name', '=',
                                                                             packaging_unit.get('cdNm', ''))])
                            if not packaging_unit_exists:
                                packaging_units_list.append({
                                    'code': packaging_unit.get('cd', ''),
                                    'name': packaging_unit.get('cdNm', ''),
                                    'description': packaging_unit.get('cdDesc', ''),
                                })
                        packaging_unit_ids = PackageUnitSudo.create(packaging_units_list)
                        packaging_units_count = len(packaging_unit_ids)
                        _logger.info(
                            f'########################## [{packaging_units_count}] VSDC Product Packaging Units Created Successfully')

                        ##########################################
                        ###### Create Payment Types in Odoo ######
                        ##########################################
                        payment_types = next(
                            item for item in json_class_list if item["cdCls"] == "07" and item["dtlList"])

                        payment_types_list = []
                        PaymentMethodSudo = self.env['vsdc.payment.method'].sudo()
                        for payment_type in payment_types.get('dtlList', []):
                            payment_type_exists = PaymentMethodSudo.search([('code', '=', payment_type.get('cd', '')),
                                                                            (
                                                                            'name', '=', payment_type.get('cdNm', ''))])
                            if not payment_type_exists:
                                payment_types_list.append({
                                    'code': payment_type.get('cd', ''),
                                    'name': payment_type.get('cdNm', ''),
                                    'description': payment_type.get('cdDesc', ''),
                                    'active': True if payment_type.get('useYn', '') == "Y" else False,
                                    'user_defined_code1': payment_type.get('userDfnCd1', ''),
                                    'user_defined_code2': payment_type.get('userDfnCd2', ''),
                                    'user_defined_code3': payment_type.get('userDfnCd3', ''),
                                })

                        payment_type_ids = PaymentMethodSudo.create(payment_types_list)
                        payment_type_count = len(payment_type_ids)
                        _logger.info(
                            f'########################## [{payment_type_count}] VSDC Payment Methods Created Successfully')

                        ##########################################
                        ### Create Sale Receipt Types in Odoo ####
                        ##########################################
                        return_reasons = next(
                            item for item in json_class_list if item["cdCls"] == "32" and item["dtlList"])
                        return_reasons_list = []
                        ReturnReasonsSudo = self.env['vsdc.return.reason'].sudo()
                        for return_reason in return_reasons.get('dtlList', []):
                            return_reason_exists = ReturnReasonsSudo.search([('code', '=', return_reason.get('cd', '')),
                                                                             ('name', '=',
                                                                              return_reason.get('cdNm', ''))])
                            if not return_reason_exists:
                                return_reasons_list.append({
                                    'code': return_reason.get('cd', ''),
                                    'name': return_reason.get('cdNm', ''),
                                    'description': return_reason.get('cdDesc', ''),
                                    'active': True if return_reason.get('useYn', '') == "Y" else False,
                                    'user_defined_code1': return_reason.get('userDfnCd1', ''),
                                    'user_defined_code2': return_reason.get('userDfnCd2', ''),
                                    'user_defined_code3': return_reason.get('userDfnCd3', ''),
                                })
                        return_reason_ids = ReturnReasonsSudo.create(return_reasons_list)
                        return_reason_count = len(return_reason_ids)
                        _logger.info(
                            f'########################## [{return_reason_count}] VSDC Refund Reasons Created Successfully')

                        ##########################################
                        ### Create Inventory Adjustment Reason in Odoo ####
                        ##########################################
                        adjustment_reasons = next(
                            item for item in json_class_list if item["cdCls"] == "35" and item["dtlList"])
                        adjustment_reasons_list = []
                        AdjustmentReasonsSudo = self.env['vsdc.inventory.adjustment.reason'].sudo()
                        for adjustment_reason in adjustment_reasons.get('dtlList', []):
                            adjustment_reason_exists = AdjustmentReasonsSudo.search(
                                [('code', '=', adjustment_reason.get('cd', '')),
                                 ('name', '=', adjustment_reason.get('cdNm', ''))])

                            if not adjustment_reason_exists:
                                adjustment_reasons_list.append({
                                    'code': adjustment_reason.get('cd', ''),
                                    'name': adjustment_reason.get('cdNm', ''),
                                    'description': adjustment_reason.get('cdDesc', ''),
                                    'active': True if adjustment_reason.get('useYn', '') == "Y" else False,
                                    'user_defined_code1': adjustment_reason.get('userDfnCd1', ''),
                                    'user_defined_code2': adjustment_reason.get('userDfnCd2', ''),
                                    'user_defined_code3': adjustment_reason.get('userDfnCd3', ''),
                                })
                        adjustment_reasons_ids = AdjustmentReasonsSudo.create(adjustment_reasons_list)
                        adjustment_reasons_count = len(adjustment_reasons_ids)
                        _logger.info(
                            f'########################## [{adjustment_reasons_count}] VSDC Inventory Adjustment Reasons Created Successfully')

                        ##########################################
                        ### Create Stock In/Out Types in Odoo ####
                        ##########################################
                        stock_in_out_types = next(
                            item for item in json_class_list if item["cdCls"] == "12" and item["dtlList"])
                        stock_in_out_types_list = []
                        StockInOutTypeSudo = self.env['vsdc.stock.in.out.type'].sudo()
                        for stock_in_out_type in stock_in_out_types.get('dtlList', []):
                            stock_in_out_type_exists = StockInOutTypeSudo.search(
                                [('code', '=', stock_in_out_type.get('cd', '')),
                                 ('name', '=', stock_in_out_type.get('cdNm', ''))])

                            if not stock_in_out_type_exists:
                                stock_in_out_types_list.append({
                                    'code': stock_in_out_type.get('cd', ''),
                                    'name': stock_in_out_type.get('cdNm', ''),
                                    'description': stock_in_out_type.get('cdDesc', ''),
                                    'active': True if stock_in_out_type.get('useYn', '') == "Y" else False,
                                    'user_defined_code1': stock_in_out_type.get('userDfnCd1', ''),
                                    'user_defined_code2': stock_in_out_type.get('userDfnCd2', ''),
                                    'user_defined_code3': stock_in_out_type.get('userDfnCd3', ''),
                                })
                        stock_in_out_type_ids = StockInOutTypeSudo.create(stock_in_out_types_list)
                        stock_in_out_types_count = len(stock_in_out_type_ids)
                        _logger.info(
                            f'########################## [{stock_in_out_types_count}] VSDC Stock In/Out Types Created Successfully')

                return self.show_message(json_response.get('resultMsg', ''))
        except Exception as e:
            _logger.info(f'######################### VSDC Exception for ({url}): {e}')

    def action_import_item_class(self):
        """Import Item Classifications from VSDC"""
        if not self.sdc_base_url or not self.vat or not self.branch_id or not self.last_request_date:
            raise ValidationError("Please provide the auth details for VSDC!")
        headers = {"Content-Type": 'application/json'}
        data = json.dumps({"tin": self.vat, "bhfId": self.branch_id, "lastReqDt": self.last_request_date})
        self.item_class_request = data
        url = f"{self.sdc_base_url}/itemClass/selectItemsClass"
        try:
            response = requests.post(url, data=data, headers=headers, verify=False)
            if response.status_code == 200:
                pprint(response.json())
                json_response = response.json()
                if json_response.get('resultCd', '') == '000':
                    self.item_class = json_response
                    json_data = json_response.get('data', {})
                    json_class_list = json_data.get('itemClsList', [])
                    if json_class_list:

                        ##########################################
                        ## Create Item Classifications Units in Odoo ##
                        ##########################################
                        item_class_list = []
                        for item_class in json_class_list:
                            item_class_list.append({
                                'code': item_class.get('itemClsCd', ''),
                                'name': item_class.get('itemClsNm', ''),
                                'level': item_class.get('itemClsLvl', ''),
                                'rra_code': item_class.get('taxTyCd', ''),
                            })
                        item_class_ids = self.env['item.classification'].sudo().create(item_class_list)
                        item_class_ids_count = len(item_class_ids)
                        _logger.info(
                            f'########################## [{item_class_ids_count}] VSDC Item Classifications Created Successfully')

        except Exception as e:
            _logger.info(f'######################### VSDC Exception for ({url}): {e}')


class ResUser(models.Model):
    _inherit = 'res.users'

    mrc = fields.Char(string="MRC", help='Machine Registration Code', unique=True)
    sdc_access_key = fields.Char(string="SDC Access Key")
    machine_serial_number = fields.Char()
    training_mode = fields.Boolean(string="Training Mode",
                                   help="If checked, all data sent to the VSDC by this user will be treated as test data")
