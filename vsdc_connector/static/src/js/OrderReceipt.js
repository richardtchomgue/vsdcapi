odoo.define('vsdc_connector.OrderReceipt', function (require) {
    "use strict";

    const rpc = require('web.rpc')

    var BaseOrderReceipt = require('point_of_sale.OrderReceipt')
    const Registries = require('point_of_sale.Registries');


    const OrderReceipt = (BaseOrderReceipt ) => {
        class OrderReceipt  extends BaseOrderReceipt {
            send_print_notification(refund=false){
                let uid = this.props.order.uid
                return rpc.query({
                    model: 'account.move',
                    method: 'mark_printed_from_ui',
                    args: [uid,refund],
                }).then(function (res) {
                });
            }

            generate_receipt_QR_code(){
                let qr;
                let stamp = this.receipt.stamp
                if (stamp && stamp.internalData) {
                    let element = document.getElementById('receipt-qr-container');
                    element.innerHTML = '<canvas id="receipt-qr-code"></canvas>'
                    // let qr_value = `${stamp.Date}#${stamp.Time}#${stamp.SNumber}#${stamp.RNumber}#${stamp.internalData}#${stamp.signature}`
                    element = document.getElementById('receipt-qr-code')
                    if (element){
                        qr = new QRious({
                            element: element,
                            size: 70,
                            value: stamp.qr_data
                        });
                    }
                }
            }
            mounted() {
                let stamp = this.props.order.stamp
                if(stamp) {
                    this.generate_receipt_QR_code()
                    if (!stamp.printed) {
                        this.send_print_notification(stamp.refund)
                    }
                }
                super.mounted()
            }
        }

        // OrderReceipt.template = 'vsdc_connector.OrderReceipt';
        return OrderReceipt;
    };
    Registries.Component.addByExtending(OrderReceipt, BaseOrderReceipt);

    return OrderReceipt;
})