import collections
import logging
import string
import unicodedata
from datetime import datetime
from decimal import Decimal
from xml.dom import minidom
from xml.parsers.expat import ExpatError

import pytz
from bs4 import BeautifulSoup
from odoo.exceptions import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

tz = pytz.timezone("Africa/Kigali")


def pad_zeroes(num, bits):
    return str(num)[:bits].zfill(bits)


def pad(s, n):
    return str(s).ljust(n)


def _dashed(s):
    return '-'.join(s[i:i + 4] for i in range(0, len(s), 4))


def _special(amount): return str(format(amount, ".2f"))


def _null(v): return 0 if type(v) in (int, float, Decimal) else ""


def clean_html(s):
    if type(s) not in [bool, int, float, Decimal]:
        return s
    return str(s or _null(s)).strip()


def success_response(response):
    """Checks whether the VSDC returned a success or an erroneous response.
    Returns True if the response is a success else False"""
    if not response:
        return
    try:
        if type(response) == dict:
            assert response["status"] == "P"
            return True
        else:
            dom = minidom.parseString(response)
            status = dom.getElementsByTagName('status')
            val = status and cleaned_value(status[0].firstChild.data)
        return val == 'P'
    except (AssertionError, ExpatError, ValueError, KeyError):
        return False


def get_error_message(response):
    """Receives the client response and returns a verbose message to display to the user"""
    if type(response) != dict:
        return str(response)
    try:
        code = response.get("code", 500)
        description = response.get("description", "")
        status = response.get("status", "E")
        assert status != "P"
        if code == 500:
            prefix = "Internal Server Error: "
        else:
            prefix = "VSDC Error: "

        return prefix + str({"code": code, "description": description})

    except AssertionError:
        return


def cleaned_value(s):
    s = str(s)
    return s.translate({ord(c): None for c in string.whitespace})


class Miner:
    """This class formats the data that is to be sent to VSDC"""

    def get_sale_receipt_data(self, invoice, on_confirmation=None):
        if not invoice.invoice_ok:
            return {}
        # journal = self.get_invoice_journal(invoice) if not invoice.training else ""
        remark = None
        if invoice.narration:
            soup = BeautifulSoup(invoice.narration, 'html.parser')
            # remark = (soup.get_text(strip=True).encode('ascii', 'ignore')).decode("utf-8")
            remark = ''.join(c for c in unicodedata.normalize('NFD', soup.get_text(strip=True))
                             if unicodedata.category(c) != 'Mn')
        confirmation_date = invoice.get_receipt_time().astimezone(tz).strftime('%Y%m%d%H%M%S')
        invoice_date = (datetime.combine(invoice.invoice_date, datetime.now().time())).astimezone(tz).strftime(
            '%Y%m%d%H%M%S') if invoice.invoice_date else None
        sales_date = invoice.get_receipt_time().astimezone(tz).strftime('%Y%m%d')
        payment_method = request.env['pos.payment.method'].search([('id', '=', invoice.payment_method_id.id)])
        receipt = {
            "custTin": invoice.partner_id.vat,
            "custMblNo": invoice.partner_id.mobile or "",
            "rptNo": invoice.receipt_number,
            "trdeNm": invoice.partner_id.name[:20],
            "adrs": invoice.partner_id.contact_address,
            "topMsg": None,
            "btmMsg": None,
            "prchrAcptcYn": "Y"
        }
        data = {
            "tin": invoice.company_id.vat,
            "bhfId": invoice.company_id.branch_id,
            "invcNo": f"{invoice.id}{invoice.name.split('/')[2]}" if invoice.name else invoice.id,
            "orgInvcNo": f"{invoice.id}{invoice.name.split('/')[2]}" if invoice.name else invoice.id,
            "custTin": invoice.partner_id.vat,
            "custNm": invoice.partner_id.name,
            "salesTyCd": "N",  # TODO
            "rcptTyCd": (invoice.move_type == "out_refund" and "R") or "S",
            "pmtTyCd": payment_method.vsdc_payment_method_id.code if payment_method else None,
            "salesSttsCd": (invoice.move_type == "out_refund" and "05") or "01",
            "cfmDt": confirmation_date,
            "salesDt": sales_date,
            "stockRlsDt": invoice_date,
            "cnclReqDt": None,
            "cnclDt": None,
            "rfdDt": invoice_date if invoice.move_type == "out_refund" else None,
            "rfdRsnCd": invoice.reason_id.code if invoice.move_type == "out_refund" else None,
            "totItemCnt": len(invoice.invoice_line_ids.filtered(lambda l: not l.display_type)),
            "taxblAmtA": invoice.taxable_a,
            "taxblAmtB": invoice.taxable_b,
            "taxblAmtC": invoice.taxable_c,
            "taxblAmtD": invoice.taxable_d,
            "taxRtA": invoice.tax_rate_a,
            "taxRtB": invoice.tax_rate_b,
            "taxRtC": invoice.tax_rate_c,
            "taxRtD": invoice.tax_rate_d,
            "taxAmtA": invoice.amount_tax_a,
            "taxAmtB": invoice.amount_tax_b,
            "taxAmtC": invoice.amount_tax_c,
            "taxAmtD": invoice.amount_tax_c,
            "totTaxblAmt": invoice.amount_total,
            "totTaxAmt": invoice.amount_tax,
            "totAmt": invoice.amount_total,
            "prchrAcptcYn": "Y",
            "remark": remark,
            "regrId": request.env.user.name,
            "regrNm": request.env.user.name,
            "modrId": request.env.user.name,
            "modrNm": request.env.user.name,
            "receipt": receipt,
            "itemList": [line.with_context(on_confirmation=on_confirmation).send_receiptitem for line in
                         invoice.invoice_line_ids if
                         line.product_id],
        }
        data = {k: clean_html(v) for k, v in data.items()}
        return data

    def get_sale_receiptitem_data(self, line, index, on_confirmation=None):
        invoice = line.move_id
        if not (line in invoice.invoice_line_ids and line.move_id.invoice_ok):
            return {}

        def _compute_tax(lyne):
            price_unit_wo_discount = lyne.price_unit * (1 - (lyne.discount / 100.0))
            tax_amt = 0
            for tax in lyne.tax_ids:
                computed = tax.compute_all(price_unit=price_unit_wo_discount,
                                           currency=invoice.company_id.currency_id,
                                           partner=invoice.partner_id,
                                           quantity=lyne.quantity,
                                           is_refund=lyne.move_id.move_type == 'out_refund',
                                           product=lyne.product_id)['taxes']
                tax_amt += computed[0]["amount"]
            return tax_amt

        discount = (line.discount or 0.0) / 100 * line.price_unit * line.quantity

        if on_confirmation:
            msg = ''
            if not line.product_id.item_code:
                msg = "Define Product Code on product."
            if not line.product_id.unspsc_categ_id.code:
                msg += 'Define UNSPSC Category Code on product.'
            if not line.product_id.quantity_unit.code:
                msg += 'Define Unit of Quantity on product.'
            if not line.product_id.packaging_unit.code:
                msg += 'Define Packaging Unit on product.'

            if not line.product_id.item_code or not line.product_id.unspsc_categ_id.code \
                    or not line.product_id.packaging_unit.code or not line.product_id.quantity_unit.code:
                raise ValidationError(f"Product Attribute Missing: {msg}")

        data = {
            "itemSeq": index,
            "itemCd": line.product_id.item_code,
            "itemClsCd": line.product_id.unspsc_categ_id.code,
            "itemNm": line.product_id.name,
            "bcd": line.product_id.barcode or None,
            "pkgUnitCd": line.product_id.packaging_unit.code,
            "pkg": 1,  # TODO
            "qtyUnitCd": line.product_id.quantity_unit.code,
            "qty": line.quantity,
            "prc": line.price_unit,
            "splyAmt": line.price_unit,  # TODO
            "dcRt": line.discount or 0,
            "dcAmt": discount,
            "isrccCd": None,
            "isrccNm": None,
            "isrcRt": None,
            "isrcAmt": None,
            "taxTyCd": (line.tax_ids and line.tax_ids[0].rra_code) or "B",
            "taxblAmt": _special(line.price_total),
            "taxAmt": _special(_compute_tax(line)),
            "totAmt": _special(line.price_total),
        }
        return {k: clean_html(v) for k, v in data.items()}

    def get_item_data(self, product, company):
        country_code = product.origin_country.code.upper() if product.origin_country else "RW"
        data = {
            'tin': company.vat,
            'bhfId': company.branch_id,
            'itemCd': product.item_code or "RW1TEST0000006",
            'itemClsCd': product.classification_code or "5059690800",
            "itemTyCd": product.rra_product_type,
            'itemNm': product.name,
            'itemStdNm': None,
            'orgnNatCd': country_code,
            'pkgUnitCd': product.packaging_unit.code,
            'qtyUnitCd': product.quantity_unit.code,
            'taxTyCd': product.taxes_ids[0].rra_code,
            'btchNo': None,
            'bcd': product.barcode or None,
            'dftPrc': product.list_price,
            'grpPrcL1': product.list_price,
            'grpPrcL2': product.list_price,
            'grpPrcL3': product.list_price,
            'grpPrcL4': product.list_price,
            'grpPrcL5': product.list_price,
            "addInfo": product.description or None,
            'sftyQty': product.qty_available or None,
            'isrcAplcbYn': "N",
            "useYn": "Y",
            "regrNm": request.env.user.name,
            "regrId": request.env.user.name,
            "modrNm": request.env.user.name,
            "modrId": request.env.user.name,
        }

        res = {k: clean_html(v) for k, v in data.items()}
        return res

    def get_inventory_data(self, picking):
        def _compute_tax(lyne):
            if lyne.prc:
                lyne_prc = lyne.prc
            else:
                lyne_prc = lyne.product_id.list_price

            if lyne.tax_id:
                lyne_tax_ids = lyne.tax_id
            else:
                lyne_tax_ids = lyne.product_id.taxes_id

            lyne_discount = lyne.discount

            if lyne.purchase_line_id:
                lyne_prc = lyne.purchase_line_id.price_unit
                lyne_tax_ids = lyne.purchase_line_id.taxes_id
            elif lyne.sale_line_id:
                lyne_prc = lyne.sale_line_id.price_unit
                lyne_tax_ids = lyne.sale_line_id.tax_id
                if lyne.sale_line_id.discount:
                    lyne_discount = lyne.sale_line_id.discount / 100 * lyne.sale_line_id.price_unit * lyne.quantity_done

            price_unit_wo_discount = lyne_prc
            if lyne_discount:
                price_unit_wo_discount = lyne_prc * (1 - (lyne_discount / 100.0))

            # tax_amt = 0
            # for tax in lyne_tax_ids:
            computed = lyne_tax_ids.compute_all(price_unit=price_unit_wo_discount,
                                                currency=picking.company_id.currency_id,
                                                partner=picking.partner_id,
                                                quantity=lyne.quantity_done,
                                                is_refund=(picking.picking_type_code == "incoming" and picking.is_sale_refund) or (picking.picking_type_code == "outgoing" and picking.is_purchase_refund),
                                                product=lyne.product_id)
            tax_amt = sum(t.get('amount', 0.0) for t in computed.get('taxes', []))
            total_included = computed["total_included"]

            return {'tax_amt': tax_amt, 'price_total': total_included}

        remark = None
        if picking.note:
            soup = BeautifulSoup(picking.note, 'html.parser')
            remark = ''.join(c for c in unicodedata.normalize('NFD', soup.get_text(strip=True))
                             if unicodedata.category(c) != 'Mn')

        sar_no = None
        orgSarNo = None
        sar_type = None

        if picking.picking_type_code == "outgoing":
            sar_type = '11'
        elif picking.picking_type_code == "incoming" and picking.is_sale_refund:
            sar_type = '12'
        elif picking.picking_type_code == "incoming":
            sar_type = '02'
        elif picking.picking_type_code == "outgoing" and picking.is_purchase_refund:
            sar_type = '03'
        elif picking.stock_in_out_id.code:
            sar_type = picking.stock_in_out_id.code

        if picking:
            sar_no = f"{picking.id}{picking.name.split('/')[2]}" if picking.name else picking.id
        if picking.location_id and picking.picking_type_code == 'internal':
            sar_no = picking.location_id.id
            orgSarNo = picking.location_dest_id.id

        picking_date = picking.date_done.strftime('%Y%m%d') if picking.date_done else None
        items = []
        for index, line in enumerate(picking.move_ids_without_package):

            msg = ''
            if not line.product_id.item_code:
                msg = "Define Product Code on product."
            if not line.product_id.unspsc_categ_id.code:
                msg += 'Define UNSPSC Category Code on product.'
            if not line.product_id.quantity_unit.code:
                msg += 'Define Unit of Quantity on product.'
            if not line.product_id.packaging_unit.code:
                msg += 'Define Packaging Unit on product.'

            if not line.product_id.item_code or not line.product_id.unspsc_categ_id.code \
                    or not line.product_id.packaging_unit.code or not line.product_id.quantity_unit.code:
                raise ValidationError(f"Product Attribute Missing: {msg}")
            if line.prc:
                prc = line.prc
            else:
                prc = line.product_id.list_price

            discount = line.discount

            if line.tax_id:
                tax_ids = line.tax_id
            else:
                tax_ids = line.product_id.taxes_id

            if line.price_total:
                price_total = line.price_total
            else:
                price_total = _compute_tax(line).get('price_total', 0)

            if line.purchase_line_id:
                prc = line.purchase_line_id.price_unit
                price_total = line.purchase_line_id.price_total
                tax_ids = line.purchase_line_id.taxes_id
            elif line.sale_line_id:
                prc = line.sale_line_id.price_unit
                price_total = line.sale_line_id.price_total
                tax_ids = line.sale_line_id.tax_id
                if line.sale_line_id.discount:
                    discount = line.sale_line_id.discount / 100 * line.sale_line_id.price_unit * line.quantity_done

            line_data = {
                "itemSeq": index,
                "itemCd": line.product_id.item_code,
                "itemClsCd": line.product_id.unspsc_categ_id.code,
                "itemNm": line.product_id.name,
                "bcd": line.product_id.barcode or None,
                "pkgUnitCd": line.product_id.packaging_unit.code,
                "pkg": line.quantity_done,  # TODO
                "qtyUnitCd": line.product_id.quantity_unit.code,
                "qty": line.quantity_done,
                "itemExprDt": None,
                "prc": prc,
                "splyAmt": prc * line.quantity_done,
                "totDcAmt": discount,
                "taxblAmt": price_total,
                "taxTyCd": (tax_ids and tax_ids[0].rra_code) or "B",
                "taxAmt": _special(_compute_tax(line).get('tax_amt', 0)),
                "totAmt": price_total,
            }
            items.append(line_data)

        amount_total = 0
        amount_tax = 0

        if picking.sale_id:
            amount_total = picking.sale_id.amount_total
            amount_tax = picking.pos_order_id.amount_tax

        if picking.purchase_id:
            amount_total = picking.purchase_id.amount_total
            amount_tax = picking.pos_order_id.amount_tax

        if picking.pos_order_id:
            amount_total = picking.pos_order_id.amount_total
            amount_tax = picking.pos_order_id.amount_tax

        if picking.picking_type_code == 'internal':
            amount_total = sum([i.get('totAmt') for i in items])
            amount_tax = sum([float(j.get('taxAmt')) for j in items])

        data = {
            "tin": picking.company_id.vat,
            "bhfId": picking.company_id.branch_id,
            "sarNo": sar_no,
            "orgSarNo": orgSarNo if picking.picking_type_code == 'internal' else sar_no,
            "regTyCd": "M",  # TODO
            "custTin": picking.partner_id.vat if picking.partner_id else None,
            "custNm": picking.partner_id.name if picking.partner_id else None,
            "custBhfId": None,  # TODO
            "sarTyCd": sar_type,
            "ocrnDt": picking_date,
            "totItemCnt": len(items),
            "totTaxblAmt": amount_total,
            "totTaxAmt": amount_tax,
            "totAmt": amount_total,
            "remark": remark,
            "regrId": request.env.user.name,
            "regrNm": request.env.user.name,
            "modrNm": request.env.user.name,
            "modrId": request.env.user.name,
            "itemList": items,
        }
        return {k: clean_html(v) for k, v in data.items()}

    def get_purchase_data(self, invoice):
        if invoice.import_ok or not invoice.bill_ok:
            return {}

        def valid_date(date):
            return datetime.strftime(date, "%Y%m%d%H%M%S")

        def get_purchase_date():
            date = invoice.create_date.astimezone(tz).date()
            if invoice.recv_invoice_id:
                date = invoice.recv_invoice_id.create_date
            return datetime.strftime(date, "%Y%m%d")

        def get_cancel_date():
            return invoice.state == 'cancel' and valid_date(alt_dt)

        remark = None
        if invoice.narration:
            soup = BeautifulSoup(invoice.narration, 'html.parser')
            remark = ''.join(c for c in unicodedata.normalize('NFD', soup.get_text(strip=True))
                             if unicodedata.category(c) != 'Mn')
        spplrInvcNo = None
        if invoice.recv_invoice_id:
            spplrInvcNo = invoice.recv_invoice_id.spplrInvcNo

        dt = invoice.create_date.astimezone(tz)
        alt_dt = invoice.write_date.astimezone(tz)
        # recv_keys = ['invId', 'regTyCd', 'mrcNo', 'bcncNm', 'refId', 'totAmt', 'totTax', 'regusrId', 'totSplpc']
        data = {
            "tin": invoice.company_id.vat,
            "bhfId": invoice.company_id.vsdc_branch_id.branch_id,
            "invcNo": f"{invoice.id}{invoice.name.split('/')[2]}" if invoice.name and len(invoice.name.split('/')) > 2 else invoice.id,
            "orgInvcNo": f"{invoice.id}{invoice.name.split('/')[2]}" if invoice.name and len(invoice.name.split('/')) > 2 else invoice.id,
            "spplrTin": invoice.partner_id.vat,
            "spplrBhfId": invoice.recv_invoice_id.spplrBhfId if invoice.registration_type == 'A' else invoice.company_id.vsdc_branch_id.branch_id,
            "spplrNm": invoice.partner_id.name,
            "spplrInvcNo": spplrInvcNo,
            "regTyCd": invoice.registration_type,
            "pchsTyCd": "N",  # TODO
            "rcptTyCd": (invoice.move_type == "in_refund" and "R") or "P",
            "pmtTyCd": invoice.recv_invoice_id.pmtTyCd.code if invoice.registration_type == 'A' and invoice.recv_invoice_id else "01",
            "pchsSttsCd": "02",  # TODO
            "cfmDt": valid_date(dt),
            "pchsDt": get_purchase_date(),
            "wrhsDt": valid_date(dt),
            "cnclReqDt": get_cancel_date(),
            "cnclDt": get_cancel_date(),
            "rfdDt": invoice.state == 'cancel' and valid_date(alt_dt),
            "totItemCnt": len(invoice.invoice_line_ids.filtered(lambda l: not l.display_type)),
            "taxblAmtA": invoice.taxable_a,
            "taxblAmtB": invoice.taxable_b,
            "taxblAmtC": invoice.taxable_c,
            "taxblAmtD": invoice.taxable_d,
            "taxRtA": invoice.tax_rate_a,
            "taxRtB": invoice.tax_rate_b,
            "taxRtC": invoice.tax_rate_c,
            "taxRtD": invoice.tax_rate_d,
            "taxAmtA": invoice.amount_tax_a,
            "taxAmtB": invoice.amount_tax_b,
            "taxAmtC": invoice.amount_tax_c,
            "taxAmtD": invoice.amount_tax_c,
            "totTaxblAmt": invoice.amount_total,
            "totTaxAmt": invoice.amount_tax,
            "totAmt": invoice.amount_total,
            "remark": remark,
            "regrNm": request.env.user.name,
            "regrId": request.env.user.name,
            "modrNm": request.env.user.name,
            "modrId": request.env.user.name,
            "itemList": [line.send_purchaseitem for line in
                         invoice.invoice_line_ids if
                         line.product_id]
        }

        # data = {
        #     "invId": invoice.receipt_number,
        #     "bcncId": invoice.partner_id.vat,
        #     "mrcNo": invoice.create_uid.mrc,
        #     "bhfId": "00",
        #     "sdcId": invoice.company_id.sdc_id,
        #     "bcncNm": invoice.partner_id.name,
        #     "bcncSdcId": invoice.partner_id.sdc_id,
        #     "bcncMrcNo": invoice.partner_id.mrc,
        #     "refId": invoice.recv_invoice_id.refId if invoice.recv_invoice_id else "",
        #     "regTyCd": invoice.registration_type,
        #     "invStatusCd": "02",  # FIX ME: replace with dynamic value,
        #     "ocde": datetime.strftime(dt, "%Y%m%d"),
        #     "validDt": valid_date(dt),
        #     "cancelReqDt": get_cancel_date(),
        #     "cancelDt": get_cancel_date(),
        #     "refundDt": invoice.state == 'cancel' and valid_date(alt_dt),
        #     "cancelTyCd": "",
        #     "totTax": _special(invoice.amount_tax),
        #     "totAmt": _special(invoice.amount_total),
        #     "totSplpc": _special(invoice.amount_total),
        #     "regusrId": (invoice.activity_user_id or invoice.user_id).name.split(" ")[0],
        #     "regDt": datetime.strftime(dt, "%Y%m%d%H%M%S"),
        #     "remark": invoice.narration,
        #     "totNumItem": len(invoice.invoice_line_ids),
        #     "payTyCd": "02",  # FIX ME:  get the real code dynamically
        #     "items": [line.send_purchaseitem for line in invoice.invoice_line_ids if
        #               line.product_id and line.price_total > 0]
        # }
        # if invoice.recv_invoice_id:
        # recv_inv = invoice.recv_invoice_id
        # data.update({"sdc_rec_id": invoice.recv_invoice_id.sdc_rec_id,
        #              "bcncSdcId": recv_inv.bcncSdcId,
        #              "bcncMrcNo": recv_inv.bcncMrcNo})
        data = {k: clean_html(v) for k, v in data.items()}
        # tax_details = self.get_tax_details(invoice.invoice_line_ids, invoice.company_id, invoice.partner_id,
        #                                    is_refund=(invoice.move_type == 'in_refund'))
        # data.update(tax_details)

        return data

    def get_purchaseitem_data(self, line, index, ):
        invoice = line.move_id
        company = line.company_id

        if not (line in invoice.invoice_line_ids and invoice.bill_ok and not invoice.import_ok):
            return {}

        def get_supplier_info(seller_ids, vendor):
            for seller in seller_ids:
                if seller == vendor:
                    return {"product_code": seller.product_code, "categ_code": seller.categ_code,
                            "product_name": seller.product_name}
            return

        def _compute_tax():
            tax_amt = 0
            for tax in line.tax_ids:
                computed = \
                    tax.compute_all(price_unit=line.price_unit, currency=company.currency_id,
                                    partner=invoice.partner_id,
                                    quantity=line.quantity,
                                    is_refund=line.price_total < 0,
                                    product=line.product_id)[
                        'taxes']
                tax_amt += computed[0]["amount"]
            return tax_amt

        seller_info = get_supplier_info(line.product_id.seller_ids, line.partner_id)
        discount = (line.discount or 0.0) / 100 * line.price_unit * line.quantity

        pkg = 1
        if line.recv_line_id:
            pkg = line.recv_line_id.pkg

        itemSeq = index
        if line.recv_line_id:
            itemSeq = line.recv_line_id.itemSeq



        # recv_keys = ['invId', 'refId', 'itemNm', 'itemCd', 'itemSeq', 'itemClsCd', 'regTyCd', 'tax', 'totAmt',
        #              'totTaxablAmt', 'dcRate', 'dcAmt']
        data = {
           "itemSeq": itemSeq,
           "itemCd": line.product_id.item_code,
           "itemClsCd": line.product_id.classification_code or "51000000",
           "itemNm": line.product_id.name,
           "bcd": line.product_id.barcode or None,
           "spplrItemClsCd": line.recv_line_id.itemClsCd if line.recv_line_id else None,
           "spplrItemCd": line.recv_line_id.itemCd if line.recv_line_id else None,
           "spplrItemNm": line.recv_line_id.itemNm if line.recv_line_id else None,
           "pkgUnitCd": line.product_id.packaging_unit.code,
           "pkg": pkg,
           "qtyUnitCd": line.product_id.quantity_unit.code,
           "qty": _special(line.quantity),
           "prc": _special(line.price_unit),
           "splyAmt": _special(line.product_id.standard_price),
           "dcRt": _special(discount),
           "dcAmt": _special(discount),
           "taxblAmt": _special(line.price_reduce * line.quantity),
           "taxTyCd": (line.tax_ids and line.tax_ids[0].rra_code) or "B",
           "taxAmt": _special(_compute_tax()),
           "totAmt": _special(line.price_total),
           "itemExprDt": None
        }

        # data = {
        #     "invId": invoice.receipt_number,
        #     "refId": invoice.recv_invoice_id.refId if invoice.recv_invoice_id else "",
        #     "itemSeq": [line.id for line in invoice.invoice_line_ids].index(line.id) + 1,
        #     "itemClsCd": line.product_id.classification_code or "51000000",
        #     "itemCd": line.product_id.item_code,
        #     "itemNm": line.product_id.name,
        #     "bcncId": line.partner_id.vat,
        #     "bhfId": "",
        #     "bcncItemClsCd": seller_info and seller_info["categ_code"],
        #     "bcncItemCd": seller_info and seller_info["product_code"],
        #     "bcncItemNm": seller_info and seller_info["product_name"],
        #     "pkgUnitCd": line.product_id.packaging_unit.code,
        #     "pkgQty": 1,
        #     "qtyUnitCd": line.product_id.quantity_unit.code,
        #     "qty": _special(line.quantity),
        #     "expirDt": "",  # line.product_id.life_time and line.product_id.life_time.date,
        #     "untpc": _special(line.price_unit),
        #     "splpc": _special(line.product_id.standard_price),
        #     "dcRate": _special(line.discount),
        #     "dcAmt": _special(discount),
        #     "taxablAmt": _special(line.price_reduce * line.quantity),
        #     "taxTyCd": (line.tax_ids and line.tax_ids[0].rra_code) or "B",
        #     "tax": _special(_compute_tax()),
        #     "totAmt": _special(line.price_total),
        #     "regTyCd": "A" if line.recv_line_id else "M",
        # }
        # if line.recv_line_id:
        #     data.update({'sdc_rec_id': line.recv_line_id.sdc_rec_id})
        return {k: clean_html(v) for k, v in data.items()}

    def get_tax_details(self, lines, company, vendor, is_refund=False):
        tax_amounts = {}
        for line in lines:
            for tax in line.tax_ids:
                vals = tax.compute_all(price_unit=line.price_reduce, currency=company.currency_id, partner=vendor,
                                       quantity=line.quantity, is_refund=is_refund, product=line.product_id)
                taxes = vals['taxes']

                if taxes:
                    agg_amounts = {'rate': tax.amount}
                    computed_amounts = taxes[0]
                    computed_amounts.update({'base': vals['total_included']})
                    key = tax.rra_code
                    prev_amounts = tax_amounts[key] if key in tax_amounts else {"amount": 0.0, "base": 0.0}
                    agg_amounts.update(
                        {k: v + prev_amounts[k] for k, v in computed_amounts.items() if k in prev_amounts})
                    tax_amounts.update({key: agg_amounts})
        rates = taxables = taxes = {}
        for code, values in tax_amounts.items():
            rates.update({f'taxRate{code}': values["rate"]})
            taxables.update({f'totTaxablAmt{code}': values["base"]})
            taxes.update({f'totTax{code}': values["amount"]})
        for code in "ABCD":
            if code not in tax_amounts:
                rates.update({f'taxRate{code}': 0})
                taxables.update({f'totTaxablAmt{code}': 0})
                taxes.update({f'totTax{code}': 0})
        result = {**rates, **taxables, **taxes}
        return {k: _special(v) for k, v in result.items()}

    def get_import_item_data(self, item):
        if item.state not in ['approved', 'rejected']:
            return {}
        status_codes = {'waiting': '2', 'approved': '3', 'rejected': '4'}
        data = {
            "tin": item.company_id.vat,
            "bhfId": item.company_id.vsdc_branch_id.branch_id,
            "taskCd": item.taskCd,
            "dclDe": item.dclDe,
            "itemSeq": item.itemSeq,
            "hsCd": item.hsCd,
            "imptItemSttsCd": status_codes[item.state],
            "remark": "remark",
            "modrNm": request.env.user.name,
            "modrId": request.env.user.name
        }

        # {
        #     "sdc_rec_id": item.sdc_rec_id,
        #     "approvalStatusCd": status_codes[item.state],
        # }
        move_line = item.move_line_ids and item.move_line_ids[0]
        if move_line:
            product = move_line.product_id
            data.update({'itemCd': product.item_code, 'itemClsCd': product.classification_code})
        return {k: clean_html(v) for k, v in data.items()}

    def get_invoice_payment_methods(self, invoice):
        sign = -1 if invoice.move_type == 'out_refund' else 1
        try:
            orders = invoice.pos_order_ids
            result = ''''''
            if orders:
                for order in orders:
                    for payment in order.payment_ids.filtered(lambda pmt: pmt.amount > 0):
                        result += f'{pad(payment.payment_method_id.name, 24)}{payment.amount * sign}RWF'
                return result
        except AttributeError:
            pass
        return f'{pad("CREDIT", 24)}{_special(invoice.amount_total * sign)}RWF'

    def get_receipt_date_and_time(self, dt):
        dt = dt.astimezone(tz)
        date = datetime.strftime(dt, '%d/%m/%Y')
        time = datetime.strftime(dt, '%H:%M:%S')
        return {"date": date, "time": time}

    def formatted_line(self, line):
        rra_code = (line.tax_ids and line.tax_ids[0].rra_code) or ""
        sign = -1 if line.move_id.move_type == 'out_refund' else 1
        amt_line = f'{line.quantity} x {_special(line.price_total / line.quantity * sign)}'
        if not line.discount:
            return f'''{line.product_id.name}
{pad(amt_line, 24)}{_special(line.price_total * sign)}{rra_code}
'''
        return f'''{line.product_id.name}
{_special(line.price_unit * sign)}
Discount {line.discount}%
{pad(amt_line, 24)}{_special(line.price_total * sign)}{rra_code}'''

    def get_taxes_journal(self, invoice):
        sign = -1 if invoice.move_type == 'out_refund' else 1
        taxes = self.get_tax_details(invoice.invoice_line_ids, invoice.company_id, invoice.partner_id,
                                     is_refund=(invoice.move_type == 'out_refund'))
        all_taxes = {}
        for line in invoice.invoice_line_ids:
            for tax in line.tax_ids:
                if tax.rra_code == 'B':
                    all_taxes.update({"B": {"label": tax.label, "amount": float(taxes["totTaxablAmtB"])}})
                    all_taxes.update({"B1": {"label": "TAX B", "amount": float(taxes["totTaxB"])}})
                else:
                    all_taxes.update({tax.rra_code: {"label": tax.label, "amount": (
                        line.price_total if tax.rra_code not in all_taxes else all_taxes[tax.rra_code][
                                                                                   'amount'] + line.price_total)}})
        result = f'''{pad("TOTAL", 24)}{_special(invoice.amount_total * sign)}RWF'''
        ordered_taxes = collections.OrderedDict(sorted(all_taxes.items()))
        for code, obj in ordered_taxes.items():
            label = obj["label"]
            amount = obj["amount"]
            result += f'\n{pad(f"TOTAL {label}", 24)}{_special(amount * sign)}RWF'
        return result

    def get_header_info(self, invoice):
        client = invoice.partner_id
        if invoice.move_type == 'out_refund':
            res = f"""REFUND
REF. NORMAL RECEIPT#: {invoice.reversed_entry_id.receipt_number}
-------------------------------------
REFUND IS APPROVED ONLY FOR
ORIGINAL SALES RECEIPT
Client ID: {client.vat or ""}"""
        else:
            res = f"""Client ID: {client.vat or ""}"""
        return res

    def get_invoice_journal(self, invoice):
        sign = -1 if invoice.move_type == 'out_refund' else 1
        company = invoice.company_id
        user = invoice.create_uid
        dt = self.get_receipt_date_and_time(invoice.get_receipt_time())
        res = f"""
            {company.name}
       Tel:{company.phone or ''}
    Email:{company.email or ''}
         TIN:{company.vat or ''}
-------------------------------------
{self.get_header_info(invoice)}
-------------------------------------
{''.join([self.formatted_line(line) for line in invoice.invoice_line_ids if line.product_id])}
-------------------------------------
{self.get_taxes_journal(invoice)}
{pad(f"TOTAL TAX", 24)}{_special(invoice.amount_tax * sign)}RWF
-------------------------------------
{self.get_invoice_payment_methods(invoice)}
{pad('ITEMS NUMBER', 24)}{len(invoice.invoice_line_ids)}
-------------------------------------
            SDC INFORMATION
Date :<date>        Time: <time>
SDC ID:                 <sdcId>
RECEIPT NUMBER:         <sdcRcptNo>/<totSdcRcptNo><rLabel>
            Internal Data
   <internalData>
          Receipt Signature
         <signature>
-------------------------------------
RECEIPT NUMBER:        {invoice.receipt_number + invoice.copies_count}
Date:{dt["date"]}        Time:{dt["time"]} 
MRC:                   {user.mrc or ""}
-------------------------------------
End of Legal Receipt
"""

        stamp = invoice.stamp
        if stamp:
            info = {
                '<date>': stamp.date,
                '<time>': stamp.time,
                '<sdcId>': stamp.s_number,
                '<sdcRcptNo>': stamp.r_number,
                '<totSdcRcptNo>': stamp.g_number,
                '<rLabel>': stamp.r_label,
                '<internalData>': _dashed(stamp.internal_data),
                '<signature>': _dashed(stamp.signature),

            }
            for k, v in info.items():
                res = res.replace(k, str(v))
        return res
