from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = (
        ('Customer', 'Customer'),
        ('Cashier', 'Cashier'),
        ('Serving Desk', 'Serving Desk'),
        ('Kitchen Manager', 'Kitchen Manager'),
        ('Cafeteria Manager', 'Cafeteria Manager'),
        ('Cafeteria Owner', 'Cafeteria Owner'),
        ('University', 'University'),
    )
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='Customer')
    is_veg_mode = models.BooleanField(default=False)
    dark_theme = models.BooleanField(default=False)
    profile_pic = models.ImageField(upload_to='profiles/', blank=True, null=True)

class SystemSettings(models.Model):
    default_pickup_wait_time_minutes = models.PositiveIntegerField(default=5)

    def save(self, *args, **kwargs):
        self.pk = 1
        super(SystemSettings, self).save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

class MenuItem(models.Model):

    CATEGORY_CHOICES = [
        ('Meals', 'Meals'),
        ('Snacks', 'Snacks'),
        ('Beverages', 'Beverages'),
        ('Desserts', 'Desserts'),
        ('Combos', 'Combos'),
        ('South Indian', 'South Indian'),
        ('North Indian', 'North Indian'),
        ('Chinese', 'Chinese'),
    ]
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_veg = models.BooleanField(default=True)
    image = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='Snacks')
    is_available = models.BooleanField(default=True)

    # Advanced Inventory Attributes
    prep_time_minutes = models.PositiveIntegerField(default=0)
    inventory_type = models.CharField(max_length=20, choices=[('continuous', 'Continuous'), ('batch', 'Batch'), ('fixed', 'Fixed')], default='continuous')
    current_stock = models.IntegerField(default=100)
    storage_stock = models.IntegerField(default=0)  # Renamed from ready_pool_stock

    def __str__(self):
        return self.name

class Feedback(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    session_key = models.CharField(max_length=40, null=True, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Feedback"
        ordering = ['-created_at']

class Report(models.Model):
    REPORT_STATUS = (
        ('Pending', 'Pending'),
        ('Investigating', 'Investigating'),
        ('Resolved', 'Resolved'),
        ('Dismissed', 'Dismissed'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    guest_profile = models.ForeignKey('GuestProfile', on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=50, choices=REPORT_STATUS, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    session_key = models.CharField(max_length=40, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_price(self):
        return sum(item.total_price() for item in self.items.all())

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    reserved_at = models.DateTimeField(null=True, blank=True)
    reservation_expires_at = models.DateTimeField(null=True, blank=True)

    def total_price(self):
        return self.quantity * self.menu_item.price
    
    def is_reservation_expired(self):
        """Check if the 1-minute reservation has expired"""
        if not self.reservation_expires_at:
            return False
        from django.utils import timezone
        return timezone.now() > self.reservation_expires_at

class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    guest_profile = models.ForeignKey('GuestProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    placed_by_cashier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cashier_orders')
    created_at = models.DateTimeField(auto_now_add=True)
    qr_code_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    status = models.CharField(max_length=50, default='Pending')  # Pending, Partial, Completed
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=50, default='Online')
    is_disabled = models.BooleanField(default=False)
    
    # Live tracking / Wait Time Logic
    ready_at = models.DateTimeField(null=True, blank=True)
    pickup_deadline = models.DateTimeField(null=True, blank=True)
    extra_time_requested = models.PositiveIntegerField(default=0)
    extra_time_status = models.CharField(max_length=50, default='None')  # None, Pending, Accepted, Rejected

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price_at_time = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50, default='Pending')  # Pending, Ready, Served

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    session_key = models.CharField(max_length=40, null=True, blank=True)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

class GuestProfile(models.Model):
    session_key = models.CharField(max_length=40)
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"

class PushSubscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='push_subscriptions')
    session_key = models.CharField(max_length=40, null=True, blank=True)
    endpoint = models.URLField(max_length=1024, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PushSub for {self.user or self.session_key}"
