odoo.define("vsdc_connector.models", function(require) {
    "use strict";

    var utils = require('web.utils');
    var round_pr = utils.round_precision;
    var ajax = require('web.ajax');
    var pos_models = require('point_of_sale.models')
    var models = pos_models.PosModel.prototype.models;
    var rpc = require('web.rpc');
    var session = require('web.session');
    var core = require('web.core');

    pos_models.load_fields("res.partner", ["street2", "tax_payer_status"]);
    pos_models.load_fields("res.company", ["street", "street2", "city"]);
    pos_models.load_fields("product.product", ["item_code"]);

    var _r = (val,refund=false) =>{
        let sign = 1
        if (refund){
            sign = -1
        }
        return ((Math.round(val * 100) / 100) * sign).toFixed(2);
    }

    for(var i=0; i<models.length; i++){

        var model=models[i];

        // Add default customer and default tax fields
        if(model.model === 'res.company'){
            model.fields.push('default_customer', 'account_sale_tax_id');

        }

        //add mrc field for displaying on receipt
        if(model.model === 'res.users'){
            model.fields.push('mrc');

        }
        if(model.model === 'account.tax'){
            model.fields.push('amount','rra_code','label');
        }
        if(model.model === 'product.product'){
            model.fields.push('type');
        }

    }

    var _super_orderline = pos_models.Orderline.prototype;
    pos_models.Orderline = pos_models.Orderline.extend({
        get_tax_base: function () {
            return this.get_all_prices().taxableAmt;
        },

        get_all_prices: function(){
            var self = this;
            var price_unit = this.get_unit_price() * (1.0 - (this.get_discount() / 100.0));
            var taxtotal = 0;
            var taxable = 0;
            var product =  this.get_product();
            var taxes_ids = product.taxes_id;
            var default_tax = this.pos.company.account_sale_tax_id
            if (!taxes_ids.length && default_tax.length && product.type !== 'service'){
                // Use default tax if no tax is specified on product
                taxes_ids.push(default_tax[0])
            }
            var taxes =  this.pos.taxes;
            var taxdetail = {};
            var product_taxes = [];
            _(taxes_ids).each(function(el){
                var tax = _.detect(taxes, function(t){
                    return t.id === el;
                });
                product_taxes.push.apply(product_taxes, self._map_tax_fiscal_position(tax));
            });
            product_taxes = _.uniq(product_taxes, function(tax) { return tax.id; });
            var all_taxes = this.pos.compute_all(product_taxes, price_unit, this.get_quantity(), this.pos.currency.rounding);
            var all_taxes_before_discount = this.pos.compute_all(product_taxes, this.get_unit_price(), this.get_quantity(), this.pos.currency.rounding);
            _(all_taxes.taxes).each(function(tax) {
                taxtotal += tax.amount;
                taxdetail[tax.id] = tax.amount;
                taxable  += tax.base
            });
            return  {
                "priceWithTax": all_taxes.total_included,
                "priceWithoutTax": all_taxes.total_included - taxtotal,
                "priceSumTaxVoid": all_taxes.total_void,
                "priceWithTaxBeforeDiscount": all_taxes_before_discount.total_included,
                "tax": taxtotal,
                "taxDetails": taxdetail,
                "taxableAmt":taxable,
            }
        },

        export_for_printing: function() {
            var line = _super_orderline.export_for_printing.apply(this,arguments);
            line.product_item_code = this.product.item_code
            return line;
        },
    });
    pos_models.PosModel = pos_models.PosModel.extend({
        print_queue : {},

        compute_all: function(taxes, price_unit, quantity, currency_rounding) {
            var self = this;

            // 1) Flatten the taxes.

            var _collect_taxes = function(taxes, all_taxes){
                taxes.sort(function (tax1, tax2) {
                    return tax1.sequence - tax2.sequence;
                });
                _(taxes).each(function(tax){
                    if(tax.amount_type === 'group')
                        all_taxes = _collect_taxes(tax.children_tax_ids, all_taxes);
                    else
                        all_taxes.push(tax);
                });
                return all_taxes;
            }
            var collect_taxes = function(taxes){
                return _collect_taxes(taxes, []);
            }

            taxes = collect_taxes(taxes);

            // 2) Avoid dealing with taxes mixing price_include=False && include_base_amount=True
            // with price_include=True

            var base_excluded_flag = false; // price_include=False && include_base_amount=True
            var included_flag = false;      // price_include=True
            _(taxes).each(function(tax){
                if(tax.price_include)
                    included_flag = true;
                else if(tax.include_base_amount)
                    base_excluded_flag = true;
                if(base_excluded_flag && included_flag)
                    throw new Error('Unable to mix any taxes being price included with taxes affecting the base amount but not included in price.');
            });

            // 3) Deal with the rounding methods

            var round_tax = this.company.tax_calculation_rounding_method != 'round_globally';

            if(!round_tax)
                currency_rounding = currency_rounding * 0.00001;

            // 4) Iterate the taxes in the reversed sequence order to retrieve the initial base of the computation.
            var recompute_base = function(base_amount, fixed_amount, percent_amount, division_amount, prec){
                return round_pr((base_amount - fixed_amount) / (1.0 + percent_amount / 100.0) * (100 - division_amount) / 100, prec);
            }

            var base = round_pr(price_unit * quantity, currency_rounding);

            var sign = 1;
            if(base < 0){
                base = -base;
                sign = -1;
            }

            var total_included_checkpoints = {};
            var i = taxes.length - 1;
            var store_included_tax_total = true;

            var incl_fixed_amount = 0.0;
            var incl_percent_amount = 0.0;
            var incl_division_amount = 0.0;

            var cached_tax_amounts = {};

            _(taxes.reverse()).each(function(tax){
                if(tax.include_base_amount){
                    base = recompute_base(base, incl_fixed_amount, incl_percent_amount, incl_division_amount, currency_rounding);
                    incl_fixed_amount = 0.0;
                    incl_percent_amount = 0.0;
                    incl_division_amount = 0.0;
                    store_included_tax_total = true;
                }
                if(tax.price_include){
                    if(tax.amount_type === 'percent')
                        incl_percent_amount += tax.amount;
                    else if(tax.amount_type === 'division')
                        incl_division_amount += tax.amount;
                    else if(tax.amount_type === 'fixed')
                        incl_fixed_amount += quantity * tax.amount
                    else{
                        var tax_amount = self._compute_all(tax, base, quantity);
                        incl_fixed_amount += tax_amount;
                        cached_tax_amounts[i] = tax_amount;
                    }
                    if(store_included_tax_total){
                        total_included_checkpoints[i] = base;
                        store_included_tax_total = false;
                    }
                }
                i -= 1;
            });
            var real_base = base
            var total_excluded = recompute_base(base, incl_fixed_amount, incl_percent_amount, incl_division_amount, currency_rounding);
            var total_included = total_excluded;

            // 5) Iterate the taxes in the sequence order to fill missing base/amount values.

            base = total_excluded;

            var taxes_vals = [];
            i = 0;
            var cumulated_tax_included_amount = 0;
            _(taxes.reverse()).each(function(tax){
                if(tax.price_include && total_included_checkpoints[i] !== undefined){
                    var tax_amount = total_included_checkpoints[i] - (base + cumulated_tax_included_amount);
                    cumulated_tax_included_amount = 0;
                }else
                    var tax_amount = self._compute_all(tax, base, quantity, true);

                tax_amount = round_pr(tax_amount, currency_rounding);

                if(tax.price_include && total_included_checkpoints[i] === undefined)
                    cumulated_tax_included_amount += tax_amount;

                taxes_vals.push({
                    'id': tax.id,
                    'name': tax.name,
                    'amount': sign * tax_amount,
                    'base': sign * round_pr(real_base, currency_rounding),
                });

                if(tax.include_base_amount)
                    base += tax_amount;

                total_included += tax_amount;
                i += 1;
            });

            return {
                'taxes': taxes_vals,
                'total_excluded': sign * round_pr(total_excluded, this.currency.rounding),
                'total_included': sign * round_pr(total_included, this.currency.rounding),
            }
        },
    })

    var _super_order = pos_models.Order.prototype;
    pos_models.Order = pos_models.Order.extend({
        export_as_JSON: function() {
            let res =  _super_order.export_as_JSON.apply(this, arguments);
            res.reversed = this.reversed
            return res
        },
        init_from_JSON: function(json) {
            let res =  _super_order.init_from_JSON.apply(this, arguments);
            this.reversed = json.reversed
            console.log("initializing from json")
            return res
        },

        refresh_stamp: async function(refund=false,refund_reason='') {
            var self = this;
            await ajax.jsonRpc(
                '/get-receipt-stamp',
                "call", {"uid": self.uid,"refund":refund,"refund_reason":refund_reason},
            ).then(function (data) {
                let code = data["code"]
                let stamp = code === 0 && data["stamp"]
                self.stamp = stamp
                self.reversed = stamp.refund
                if(code !== 0){
                    self.stamp_error = data["message"]
                }
                return stamp
            }).catch(function (error) {
                if (error) {
                    console.error(error)
                }
                return false
            })

        },
        get_tax_details: function(){
            var details = {};
            var fulldetails = [];

            this.orderlines.each(function(line){
                var ldetails = line.get_tax_details();
                var base_amt = line.get_tax_base()
                for(var id in ldetails){
                    if(ldetails.hasOwnProperty(id)){
                        let amt = ldetails[id]
                        if (details[id]){
                            details[id].amount += amt;
                            details[id].base += base_amt;
                        }else{
                            details[id] = {amount:amt,base:base_amt}
                        }
                    }
                }
            });

            for(var id in details){
                if(details.hasOwnProperty(id)){
                    fulldetails.push({amount: details[id].amount, tax: this.pos.taxes_by_id[id], name: this.pos.taxes_by_id[id].name, base:details[id].base});
                }
            }
            return fulldetails;
        },
        getOrderReceiptEnv: function() {
            let res =  {
                order: this,
                receipt: this.export_for_printing(),
                orderlines: this.get_orderlines(),
                paymentlines: this.get_paymentlines(),
            }
            _.each(res.orderlines,function(line){
                let tax_codes = _.map(line.get_applicable_taxes(), function(tax){ return tax.rra_code; })
                if(tax_codes.length){
                    _.each(res.receipt.orderlines, function(_line){
                        if(_line.id === line.id){
                            _line.tax_code = tax_codes[0]
                            return false
                        }
                    })
                }
            })
            let refund = this.stamp.refund
            res.receipt.orderlines
            res.receipt.stamp = this.stamp
            if(!res.receipt.date.localestring){
                res.receipt.date.localestring = res.receipt.date.validation_date
            }
            _.each(res.receipt.orderlines,function (line){
                line.price_display = _r(line.price_display,refund)
                line.price_display_one = _r(line.price_display_one,refund)
                line.price_lst = _r(line.price_lst,refund)
                line.price_with_tax_before_discount = _r(line.price_with_tax_before_discount,refund)
                line.price = _r(line.price,refund)
            })
            res.receipt._r = _r
            return res
        },

        export_for_printing: function() {
            const receipt = _super_order.export_for_printing.apply(this, arguments);
            receipt.company['street'] = this.pos.company.street;
            receipt.company['street2'] = this.pos.company.street2;
            receipt.company['city'] = this.pos.company.city;

            return receipt
        },


    })

})