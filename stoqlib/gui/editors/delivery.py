# -*- Mode: Python; coding: iso-8859-1 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2005, 2006 Async Open Source <http://www.async.com.br>
## All rights reserved
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU Lesser General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU Lesser General Public License for more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307,
## USA.
##
## Author(s): Henrique Romano           <henrique@async.com.br>
##            Evandro Vale Miquelito    <evandro@async.com.br>
##
""" Product delivery editor implementation """

import gettext
import gtk

from kiwi.ui.widgets.list import Column
from stoqlib.gui.base.lists import AdditionListSlave, SimpleListDialog
from stoqlib.gui.base.editors import BaseEditor, NoteEditor
from stoqlib.gui.base.columns import ForeignKeyColumn
from stoqlib.gui.base.dialogs import run_dialog

from stoqlib.lib.parameters import sysparam
from stoqlib.lib.validators import format_quantity, get_price_format_str
from stoqlib.domain.sellable import AbstractSellable
from stoqlib.domain.service import ServiceSellableItem, DeliveryItem
from stoqlib.domain.sale import Sale
from stoqlib.domain.interfaces import IDelivery
from stoqlib.gui.editors.sellable import SellableItemEditor

_ = lambda msg: gettext.dgettext('stoqlib', msg)


class DeliveryEditor(BaseEditor):
    model_name = _('Delivery')
    model_type = ServiceSellableItem
    gladefile = 'DeliveryEditor'
    title = _('New Delivery')
    size = (600, 500)

    delivery_widgets = ('delivery_address',)
    sellableitem_widgets = ('price',
                            'delivery_date')

    def __init__(self, conn, sale=None, products=None):
        self.products = products
        self.sale = sale
        BaseEditor.__init__(self, conn)
        self.additional_info_label.set_size('small')
        self.additional_info_label.set_color('Red')
        self.register_validate_function(self._validate_widgets)
        self.update_widgets()

    def _validate_widgets(self, validation_value):
        if not self.delivery.get_items().count():
            validation_value = False
        self.refresh_ok(validation_value)

    def set_widgets_format(self):
        self.price.set_data_format(get_price_format_str())

    def update_widgets(self):
        if self.model.notes:
            self.additional_info_label.show()
        else:
            self.additional_info_label.hide()

    def _check_products(self):
        if not self.products:
            raise TypeError("This editor (%r) requires a list of "
                            "ProductAdaptToSellableItem objects, "
                            "since you don't have a model defined"
                            % self)

    def _check_sale(self):
        if not self.sale:
            raise TypeError("This editor (%r) requires a valid "
                            "Sale object, since you don't have "
                            "a model defined." % self)

    def _check_client_addresses(self):
        if not self.sale.client.get_adapted().get_main_address():
            raise TypeError("The client "%r" doesn't have a main "
                            "address" % self.sale.client)

    def _create_delivery_items(self):
        delivery_items = []
        for product in self.products:
            if product.has_been_totally_delivered():
                continue
            item = self.delivery.add_item(product)
            delivery_items.append(item)
        self.delivery_items = delivery_items

    #
    # Callbacks
    #

    def before_delete_items(self, slave, items):
        delivery = IDelivery(self.model, connection=self.conn)
        delivery.remove_items(items)
        self.force_validation()

    def on_change_address_button__clicked(self, button):
        cols = [Column('address_string', title=_('Address'), data_type=str, 
                       expand=True),
                Column('city', title=_('City'), width=100, data_type=str),
                Column('state', title=_('State'), data_type=str)]

        addresses = self.model.sale.client.get_adapted().addresses
        result = run_dialog(SimpleListDialog, self, cols, 
                            addresses, title=_('Client Addresses'),
                            selection_mode=gtk.SELECTION_BROWSE)
        if result:
            assert isinstance(result, list) and len(result) == 1
            result = result[0]
            text = result.get_address_string()
            self.delivery_address.set_text(text)

    def on_additional_info_button__clicked(self, button):
        if run_dialog(NoteEditor, self, self.conn, self.model, 'notes',
                      title=_('Delivery Instructions')):
            self.update_widgets()

    # 
    # BaseEditor hooks
    #

    def get_title_model_attribute(self, model):
        return self.model_name

    def create_model(self, conn):
        self._check_products()
        self._check_sale()
        self._check_client_addresses()

        sale = Sale.get(self.sale.id, connection=conn)
        service = sysparam(conn).DELIVERY_SERVICE
        model = service.add_sellable_item(sale)
        self.delivery = model.addFacet(IDelivery, connection=conn)
        self._create_delivery_items()

        main_address = sale.client.get_adapted().get_main_address()
        address_string = ("%s - %s/%s" 
                          % (main_address.get_address_string(),
                             main_address.get_city(), 
                             main_address.get_state()))
        self.delivery.delivery_address = address_string
        return model

    def setup_proxies(self):
        self.set_widgets_format()
        delivery = IDelivery(self.model, connection=self.conn)
        self.add_proxy(delivery, DeliveryEditor.delivery_widgets)
        self.add_proxy(self.model, DeliveryEditor.sellableitem_widgets)

    def setup_slaves(self):
        columns = [ForeignKeyColumn(AbstractSellable, 'code', title=_('Code'), 
                                    data_type=str, sorted=True,
                                    obj_field='sellable'),
                   ForeignKeyColumn(AbstractSellable, 
                                    'base_sellable_info.description',
                                    title=_('Description'), data_type=str, 
                                    expand=True, obj_field='sellable'),
                   Column('quantity', title=_('Quantity'), data_type=float, 
                          format_func=format_quantity)]

        delivery = IDelivery(self.model, connection=self.conn)
        items = delivery.get_items()
        self.slave = AdditionListSlave(self.conn, columns,
                                       SellableItemEditor, items)
        self.slave.register_editor_kwargs(model_type=DeliveryItem,
                                          restrict_increase_qty=True)
        self.slave.hide_add_button()
        self.slave.connect('before-delete-items', self.before_delete_items)
        self.attach_slave('addition_list_holder', self.slave)

    def on_cancel(self):
        delivery = IDelivery(self.model, connection=self.conn)
        delivery.remove_items(delivery.get_items())
        table = type(delivery)
        table.delete(delivery.id, connection=self.conn)
        self.model_type.delete(self.model.id, connection=self.conn)
        return BaseEditor.on_cancel(self)

