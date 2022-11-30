odoo.define('vsdc_connector.ReprintReceiptButton', function (require) {
    'use strict';

    const ReprintButton = require('point_of_sale.ReprintReceiptButton');
    const Registries = require('point_of_sale.Registries');

    const vsdc_connectorReprintButton = (ReprintButton) =>
        class extends ReprintButton {
            async showScreen(name, props) {
                if (name === 'ReprintReceiptScreen') {
                    let order = props.order
                    await order.refresh_stamp()
                    if (order.stamp) {
                        return super.showScreen(name, props)
                    } else {
                        let error = order.stamp_error || "The system could not establish connection with the VSDC"
                        const {confirmed} = await this.showPopup('ConfirmPopup', {
                            title: this.env._t('Error!'),
                            body: this.env._t(`${error}. Would you like to retry?`),
                            confirmText: this.env._t('Yes'),
                            cancelText: this.env._t('Later'),
                        });
                        if (confirmed) {
                            return await this.showScreen(name,props)
                        }
                        return
                    }
                }
                return super.showScreen(name, props)

            }
        }
    Registries.Component.extend(ReprintButton, vsdc_connectorReprintButton)
    return ReprintButton
})