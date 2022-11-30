odoo.define('vsdc_connector.TicketScreen', function (require) {
    "use strict";

    var BaseTicketScreen = require('point_of_sale.TicketScreen')
    const Registries = require('point_of_sale.Registries');
    const { isConnectionError } = require('point_of_sale.utils');


    const TicketScreen = (BaseTicketScreen ) => {
        class TicketScreen  extends BaseTicketScreen {
            async _onDoRefund() {
                const order = this.getSelectedSyncedOrder();
                if (!order) return;

                if (!order.reversed){
                    try {
                        var refundReasons = await this.rpc({
                            model: 'vsdc.return.reason',
                            method: 'search_read',
                            domain: [],
                            fields: ['id', 'code', 'name'],
                        });
                    } catch (error) {
                        if (isConnectionError(error)) {
                            return this.showPopup('OfflineErrorPopup', {
                                title: this.env._t('Network Error'),
                                body: this.env._t("Lots is not loaded. Tried loading the lots from the server but there is a network error."),
                            });
                        } else {
                            throw error;
                        }
                    }
                    const { confirmed, payload: refundReason } = await this.showPopup('TextAreaPopup', {
                        title: this.env._t('Enter the refund reason'),
                        reasons: refundReasons,
                        confirmText: this.env._t('Reverse'),
                        cancelText: this.env._t('Cancel'),
                    });

                    if (confirmed) {
                        await order.refresh_stamp(true, refundReason)
                    }else{
                        return
                    }
                }else{
                 await order.refresh_stamp(true)
                }
                if (order.stamp) {
                    this.env.pos._invalidateSyncedOrdersCache([order.uid]);
                    await this._fetchSyncedOrders();
                    return this.showScreen('ReprintReceiptScreen', { order: order});
                } else {
                    let error = order.stamp_error || "The system could not establish connection with the VSDC"
                    const {confirmed} = await this.showPopup('ConfirmPopup', {
                        title: this.env._t('Error!'),
                        body: this.env._t(`${error}. Would you like to retry?`),
                        confirmText: this.env._t('Yes'),
                        cancelText: this.env._t('Later'),
                    });
                    if (confirmed) {
                        return await this._onDoRefund()
                    }
                }
            }
        }
        return TicketScreen;
    };
    Registries.Component.addByExtending(TicketScreen, BaseTicketScreen);

    return TicketScreen;
})