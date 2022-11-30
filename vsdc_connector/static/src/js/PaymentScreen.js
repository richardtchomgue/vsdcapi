odoo.define('vsdc_connector.chrome', function (require) {
    "use strict";

    var PaymentScreen = require('point_of_sale.PaymentScreen')
    const Registries = require('point_of_sale.Registries');
    const rpc = require("web.rpc")

    const vsdc_connectorPaymentScreen = (PaymentScreen) =>
        class extends PaymentScreen {
            constructor() {
                super(...arguments);
            }

            hasNegativeAmount(order) {
                if (order && order.orderlines.length) {
                    let lines = order.orderlines.models;
                    for (let i = 0; i < lines.length; i++) {
                        let line = lines[i]
                        if (line.quantity < 0) {
                            return true
                        }
                    }
                }
                return false
            }

            async checkStock(order){
                let line_models =  order.orderlines.models
                let products = {}
                _.each(line_models, function(model){
                    let product_id = model.product.id
                    products[product_id] = model.quantity
                })
                let res = []
                await rpc.query({
                    model: 'stock.quant',
                    method: 'pos_check_quantity',
                    args: [order.pos_session_id,products],
                }).then(function (data) {
                    res = data
                });
                return res
            }

            async validateOrder(isForceValidate) {
                let order = this.env.pos.get_order()
                if (this.hasNegativeAmount(order)) {
                    return this.showPopup('ErrorPopup', {
                        title: this.env._t('Refund not allowed'),
                        body: this.env._t('Negative amounts/quantities implies refund and it is not allowed here. ' +
                            'For refund please create a credit note for the corresponding invoice from the Backend')
                    });
                }
                let data = await this.checkStock(order);
                if(data.lines.length){
                    return await this.showPopup('StockPopup', {lines:data.lines,location:data.location})
                }
                else {
                    if (!order.get_client()) {
                        const {confirmed} = await this.showPopup('ConfirmPopup', {
                            title: this.env._t('Please select the Customer'),
                            body: this.env._t('You need to select the customer before you can invoice an order.'),
                        });
                        if (confirmed) {
                            return await this.showTempScreen('ClientListScreen')
                        }
                        return
                    }
                    return super.validateOrder(isForceValidate)
                }
            }
            async showScreen(name, props) {
                if (name === 'ReceiptScreen') {
                    let order = this.currentOrder
                    await order.refresh_stamp()
                    if (order.stamp) {
                        return super.showScreen(name, props)
                    }else{
                        let error = order.stamp_error || "The system could not establish connection with the VSDC"
                        const {confirmed} = await this.showPopup('ConfirmPopup', {
                            title: this.env._t('Error!'),
                            body: this.env._t(`${error}. Would you like to retry?`),
                            confirmText: this.env._t('Yes'),
                            cancelText: this.env._t('Later'),
                        });
                        if (confirmed) {
                            return await this.showScreen(name,props)
                        }else{
                            this.currentOrder.finalize()
                            return await this.showScreen('ProductScreen',undefined)
                        }
                    }
                }
                return super.showScreen(name, props)
            }

        }

    Registries.Component.extend(PaymentScreen, vsdc_connectorPaymentScreen);

    return PaymentScreen;

})