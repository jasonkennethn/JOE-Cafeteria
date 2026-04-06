from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from .models import (
	Cart,
	CartItem,
	GuestProfile,
	MenuItem,
	Notification,
	Order,
	OrderItem,
	Report,
	User,
)


class StorageRoutingTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.customer = User.objects.create_user(
			username='customer1',
			password='testpass123',
			role='Customer',
		)
		self.client.force_login(self.customer)

	def _submit_checkout(self, storage_stock, requested_qty):
		item = MenuItem.objects.create(
			name='Veg Roll',
			description='Fresh roll',
			price=Decimal('40.00'),
			category='Snacks',
			storage_stock=storage_stock,
			current_stock=200,
		)
		cart = Cart.objects.create(user=self.customer)
		CartItem.objects.create(cart=cart, menu_item=item, quantity=requested_qty)

		response = self.client.post(reverse('checkout_submit'))
		self.assertEqual(response.status_code, 302)

		order = Order.objects.latest('id')
		item.refresh_from_db()
		return order, item, cart

	def test_checkout_uses_storage_when_fully_available(self):
		order, menu_item, cart = self._submit_checkout(storage_stock=10, requested_qty=3)

		self.assertEqual(menu_item.storage_stock, 7)
		self.assertFalse(cart.items.exists())

		order_items = list(OrderItem.objects.filter(order=order))
		self.assertEqual(len(order_items), 1)
		self.assertEqual(order_items[0].status, 'Ready')
		self.assertEqual(order_items[0].quantity, 3)

	def test_checkout_splits_ready_and_pending_when_storage_partial(self):
		order, menu_item, _ = self._submit_checkout(storage_stock=2, requested_qty=5)

		self.assertEqual(menu_item.storage_stock, 0)

		ready_item = OrderItem.objects.get(order=order, status='Ready')
		pending_item = OrderItem.objects.get(order=order, status='Pending')
		self.assertEqual(ready_item.quantity, 2)
		self.assertEqual(pending_item.quantity, 3)

	def test_checkout_routes_all_to_kitchen_when_storage_empty(self):
		order, menu_item, _ = self._submit_checkout(storage_stock=0, requested_qty=4)

		self.assertEqual(menu_item.storage_stock, 0)
		order_items = list(OrderItem.objects.filter(order=order))
		self.assertEqual(len(order_items), 1)
		self.assertEqual(order_items[0].status, 'Pending')
		self.assertEqual(order_items[0].quantity, 4)


class ReportAccessAndNotificationTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.owner = User.objects.create_user(
			username='owner1',
			password='testpass123',
			role='Cafeteria Owner',
		)
		self.manager = User.objects.create_user(
			username='manager1',
			password='testpass123',
			role='Cafeteria Manager',
		)

	def test_non_customer_user_is_redirected_from_report_page(self):
		kitchen_user = User.objects.create_user(
			username='kitchen1',
			password='testpass123',
			role='Kitchen Manager',
		)
		self.client.force_login(kitchen_user)

		response = self.client.get(reverse('report'))
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse('profile'))

	def test_customer_can_submit_report_and_management_gets_notified(self):
		customer = User.objects.create_user(
			username='customer2',
			password='testpass123',
			role='Customer',
			first_name='Test',
			last_name='Customer',
		)
		self.client.force_login(customer)

		response = self.client.post(
			reverse('report'),
			{
				'subject': 'Late service',
				'description': 'Order was delayed and status was unclear.',
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse('report'))
		report = Report.objects.get(user=customer)
		self.assertEqual(report.subject, 'Late service')

		notifications = Notification.objects.filter(title='New Customer Report')
		self.assertEqual(notifications.count(), 2)
		self.assertSetEqual(
			set(notifications.values_list('user__username', flat=True)),
			{'owner1', 'manager1'},
		)

	def test_guest_can_submit_report_when_guest_profile_exists(self):
		session = self.client.session
		session['guest_bootstrap'] = True
		session.save()
		session_key = session.session_key

		guest = GuestProfile.objects.create(
			session_key=session_key,
			full_name='Guest User',
			phone_number='9998887776',
		)

		response = self.client.post(
			reverse('report'),
			{
				'subject': 'Cleanliness concern',
				'description': 'Please improve table cleanliness near serving area.',
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse('report'))

		report = Report.objects.get(guest_profile=guest)
		self.assertEqual(report.user, None)
		self.assertEqual(report.subject, 'Cleanliness concern')
