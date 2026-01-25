from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from datetime import datetime
from .models import Task


def landing(request):
    """Загрузочная страница"""
    return render(request, 'tasks/landing.html')


def task_list(request):
    """Главная страница - список задач"""
    tasks = Task.objects.all()
    return render(request, 'tasks/task_list.html', {'tasks': tasks})


def task_create(request):
    """Создание задачи"""
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        due_date_str = request.POST.get('due_date')
        
        # Конвертируем дату
        due_date = None
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%dT%H:%M")
                due_date = timezone.make_aware(due_date)
            except ValueError:
                pass
        
        Task.objects.create(
            title=title,
            description=description,
            due_date=due_date,
        )
        return redirect('task_list')
    
    return render(request, 'tasks/task_form.html', {
        'action': 'Создать',
    })


def task_update(request, pk):
    """Редактирование задачи"""
    task = get_object_or_404(Task, id=pk)
    
    if request.method == 'POST':
        task.title = request.POST.get('title')
        task.description = request.POST.get('description', '')
        
        due_date_str = request.POST.get('due_date')
        if due_date_str:
            try:
                task.due_date = timezone.make_aware(
                    datetime.strptime(due_date_str, "%Y-%m-%dT%H:%M")
                )
            except ValueError:
                pass
        else:
            task.due_date = None
        
        task.save()
        return redirect('task_list')
    
    return render(request, 'tasks/task_form.html', {
        'task': task,
        'action': 'Редактировать',
    })


def task_delete(request, pk):
    """Удаление задачи"""
    task = get_object_or_404(Task, id=pk)
    
    if request.method == 'POST':
        task.delete()
        return redirect('task_list')
    
    return render(request, 'tasks/task_confirm_delete.html', {'task': task})


def task_toggle(request, pk):
    """Переключить статус"""
    task = get_object_or_404(Task, id=pk)
    
    if task.status == 'new':
        task.status = 'in_progress'
    elif task.status == 'in_progress':
        task.status = 'done'
    else:
        task.status = 'new'
    
    task.save()
    return redirect('task_list')