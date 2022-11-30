odoo.define('vsdc_connector.ReasonLine', function(require) {
    'use strict';

    const PosComponent = require('point_of_sale.PosComponent');
    const Registries = require('point_of_sale.Registries');

    class ReasonLine extends PosComponent {
        get highlight() {
            let reason_text = ''
            let reason_id = null
            if (this.props.selectedReason !== null){
                reason_text = this.props.selectedReason.text
                reason_id = this.props.selectedReason._id
            }
            return this.props.reason.text !== reason_text && this.props.reason._id !== reason_id ? '' : 'highlight';
        }
    }
    ReasonLine.template = 'ReasonLine';
    Registries.Component.add(ReasonLine);
    return ReasonLine;
});
