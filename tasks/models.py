from django.db import models
from django.utils import timezone


class Task(models.Model):
    """Задача"""
    STATUS_CHOICES = [
        ('new', 'Новая'),
        ('in_progress', 'В процессе'),
        ('done', 'Выполнена'),
        ('overdue', 'Просрочена'),
    ]
    
    title = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='new',
        verbose_name='Статус'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(null=True, blank=True, verbose_name='Срок выполнения')
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if self.due_date and timezone.is_naive(self.due_date):
            self.due_date = timezone.make_aware(self.due_date)
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'
        ordering = ['-created_at']