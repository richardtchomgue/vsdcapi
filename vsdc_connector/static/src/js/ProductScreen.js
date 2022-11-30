odoo.define('vsdc_connector.ProductScreen', function (require) {
    'use strict';

    const ProductScreen = require('point_of_sale.ProductScreen');
    const Registries = require('point_of_sale.Registries');


    const vsdc_connectorProductScreen = (ProductScreen) =>
        class extends ProductScreen {
            constructor() {
                super(...arguments);
            }

            mounted() {
                this.setDefaultClient()
                super.mounted()
            }

            setDefaultClient(){
                let client = this.env.pos.company.default_customer
                let order = this.env.pos.get_order()
                if (order && client && !order.get_client()) {
                    let newClient = this.env.pos.db.get_partner_by_id(client[0])
                    order.set_client(newClient);
                    order.updatePricelist(newClient);
                }
            }

        }

    Registries.Component.extend(ProductScreen, vsdc_connectorProductScreen);

    return ProductScreen;

})