from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, MenuItem, Cart, CartItem, Order, OrderItem, Notification, GuestProfile

class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Custom Fields', {'fields': ('role', 'is_veg_mode', 'dark_theme', 'profile_pic')}),
    )
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'is_active']
    list_filter = ['role', 'is_active']

class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'category', 'is_veg', 'is_available', 'current_stock', 'inventory_type']
    list_filter = ['category', 'is_veg', 'is_available', 'inventory_type']
    list_editable = ['price', 'is_available', 'current_stock']

class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'guest_profile', 'total_amount', 'payment_method', 'status', 'is_disabled', 'created_at']
    list_filter = ['status', 'payment_method', 'is_disabled']

class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'menu_item', 'quantity', 'status']
    list_filter = ['status']

admin.site.register(User, CustomUserAdmin)
admin.site.register(MenuItem, MenuItemAdmin)
admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(Order, OrderAdmin)
admin.site.register(OrderItem, OrderItemAdmin)
admin.site.register(Notification)
admin.site.register(GuestProfile)
