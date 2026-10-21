# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase, tagged


@tagged('-at_install', 'post_install')
class TestIrModels(TransactionCase):

    def test_miro_gantt_in_act_window_view_mode(self):
        field = self.env['ir.actions.act_window.view']._fields['view_mode']
        selection_keys = [key for key, _ in field.selection]
        self.assertIn('miro_gantt', selection_keys)

    def test_miro_gantt_in_ui_view_type(self):
        field = self.env['ir.ui.view']._fields['type']
        selection_keys = [key for key, _ in field.selection]
        self.assertIn('miro_gantt', selection_keys)

    def test_is_qweb_based_view_true(self):
        view_model = self.env['ir.ui.view']
        self.assertTrue(view_model._is_qweb_based_view('miro_gantt'))

    def test_is_qweb_based_view_form_unchanged(self):
        view_model = self.env['ir.ui.view']
        result = view_model._is_qweb_based_view('form')
        self.assertIsInstance(result, bool)
