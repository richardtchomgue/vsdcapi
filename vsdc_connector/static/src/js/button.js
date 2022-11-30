odoo.define('product.cis_button', function (require) {
    "use strict";
    /**
     * Button 'Create' is replaced by Custom Button
     **/
    var rpc = require('web.rpc')
    var ListController = require('web.ListController');
    var core = require('web.core');
    var _t = core._t;

    ListController.include({
        renderButtons: function($node) {
            this._super.apply(this, arguments);
            if (this.$buttons) {
                this.$buttons.find('.o_list_tender_button_update_taxes').click(this.proxy('action_update_taxes'));
                this.$buttons.find('.o_list_tender_button_fetch_purchases').click(this.proxy('action_fetch_purchases'));
                this.$buttons.find('.o_list_tender_button_fetch_import_items').click(this.proxy('action_fetch_import_items'));
                this.$buttons.find('.o_list_tender_button_fetch_import_vsdc_products').click(this.proxy('action_fetch_import_vsdc_products'));
            }
        },


        action_update_taxes: function(e){
            return rpc.query({
                model: 'product.template',
                method: 'action_update_taxes',
                args: [],
            }).then(function(){
                location.reload()
            });
        },

        action_fetch_purchases: function(e){
            var self = this;
            return rpc.query({
                model: 'account.move.recv',
                method: 'action_fetch_purchases',
                args: [],
            }).then(function(status){
                if (status === false){
                    return self.do_action({
                        title: _t('VSDC Message'),
                        type: 'ir.actions.act_window',
                        res_model: 'feedback.wizard',
                        target: 'new',
                        views: [[false, 'form']],
                        context: {'default_message': "Purchase Data must be imported from Headquarters! Please check your branch in company settings"},
                    })
                }else{
                    location.reload()
                }
            });
        },

        action_fetch_import_vsdc_products: function(e){
            var self = this;
            return rpc.query({
                model: 'vsdc.product.import',
                method: 'action_fetch_vsdc_products',
                args: [],
            }).then(function(){
                    location.reload()

            });
        },

        action_fetch_import_items: function(e){
            var self = this;
            return rpc.query({
                model: 'recv.import.item',
                method: 'action_fetch_items',
                args: [],
            }).then(function(status){
                if (status === false){
                    return self.do_action({
                        title: _t('VSDC Message'),
                        type: 'ir.actions.act_window',
                        res_model: 'feedback.wizard',
                        target: 'new',
                        views: [[false, 'form']],
                        context: {'default_message': "Purchase Data must be imported from Headquarters! Please check your branch in company settings"},
                    })
                }else{
                    location.reload()
                }
            });
        }
    });

});