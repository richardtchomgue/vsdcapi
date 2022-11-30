odoo.define('vsdc_connector.TextAreaPopupExt', function(require) {
    'use strict';

    const { useState } = owl.hooks;
    const Registries = require('point_of_sale.Registries');
    const { useAutoFocusToLast } = require('point_of_sale.custom_hooks');
    const { _lt } = require('@web/core/l10n/translation');
    const TextAreaPopup = require('point_of_sale.TextAreaPopup');
    var core = require('web.core');
    var utils = require('web.utils');

    const TextAreaPopupExt = (TextAreaPopup) =>
        class extends TextAreaPopup {
            constructor() {
                super(...arguments);
                this._id = 1;
                this.state = useState({
                    reasons: this._initialize(this.props.reasons),
                    selectedReason: null,
                    record_id: ''
                });
            }

            _initialize(array) {
                // If no array is provided, we initialize with one empty item.
                if (array.length === 0) return [this._emptyItem()];
                    // Put _id for each item. It will serve as unique identifier of each item.
                return array.map((item) => Object.assign({}, { _id: this._nextId() }, { 'text': item.name}));
            }

            _nextId() {
                return this._id++;
            }

            _emptyItem() {
                return {
                    text: '',
                    _id: this._nextId(),
                };
            }

            get reasons() {
                let res = this.reasonsArray;
                return res.sort(function (a, b) { return (a.text || '').localeCompare(b.text || '') });
            }

            /*
            Create an array of reasons
            */
            get reasonsArray() {
                var reasons = []
                var reasonsArr = this.state.reasons
                if (reasonsArr.length > 0){
                    for (var i=0; i < reasonsArr.length; i++){
                        reasons.push({'_id': reasonsArr[i]._id, 'text': reasonsArr[i].text});
                    }
                }
                return reasons
            }

            clickReason(event) {
                let reason = event.detail.reason;
                let reason_text = ''
                let reason_id = null
                if (this.state.selectedReason !== null){
                    reason_text = this.state.selectedReason.text
                    reason_id = this.state.selectedReason._id
                }
                if (reason_text === reason.text && reason_id === reason._id) {
                    this.state.selectedReason = null;
                } else {
                    this.state.selectedReason = reason
                }
                this.inputRef.el.innerText = reason.text
                this.state.inputValue = reason.text
                this.state.record_id = reason._id
            }
            getPayload() {
            if (this.state.record_id){
                return {'id': this.state.record_id, 'text': this.state.inputValue}
            }else
               return this.state.inputValue;
            }
        };

    TextAreaPopup.defaultProps.reasons = [];

    Registries.Component.extend(TextAreaPopup, TextAreaPopupExt);
    return TextAreaPopup;
});
