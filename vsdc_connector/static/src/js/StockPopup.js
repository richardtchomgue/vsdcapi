odoo.define('vsdc_connector.StockPopup', function(require) {
    'use strict';

    const AbstractAwaitablePopup = require('point_of_sale.AbstractAwaitablePopup');
    const Registries = require('point_of_sale.Registries');


    class StockPopup extends AbstractAwaitablePopup {
        constructor() {
            super(...arguments);
            this.location = this.props.location
            this.lines = this.props.lines
        }

    }

    StockPopup.template = 'StockPopup';
    Registries.Component.add(StockPopup);

    return StockPopup;
});
