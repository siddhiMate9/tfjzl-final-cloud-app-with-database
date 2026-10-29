
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
import logging

from .models import (
    Course,
    Enrollment,
    Question,
    Choice,
    Submission,
)

logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}
    if request.method == 'GET':
        return render(
            request,
            'onlinecourse/user_registration_bootstrap.html',
            context,
        )

    username = request.POST['username']
    password = request.POST['psw']
    first_name = request.POST['firstname']
    last_name = request.POST['lastname']

    if User.objects.filter(username=username).exists():
        context['message'] = "User already exists."
        return render(
            request,
            'onlinecourse/user_registration_bootstrap.html',
            context,
        )

    user = User.objects.create_user(
        username=username,
        first_name=first_name,
        last_name=last_name,
        password=password,
    )
    login(request, user)
    return redirect("onlinecourse:index")


def login_request(request):
    context = {}
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['psw']
        user = authenticate(username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = "Invalid username or password."
        return render(
            request,
            'onlinecourse/user_login_bootstrap.html',
            context,
        )

    return render(request, 'onlinecourse/user_login_bootstrap.html', context)


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    if not user.is_authenticated:
        return False
    return Enrollment.objects.filter(user=user, course=course).exists()


class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]

        for course in courses:
            course.is_enrolled = check_if_enrolled(user, course)

        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_details_bootstrap.html'


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    if user.is_authenticated and not check_if_enrolled(user, course):
        Enrollment.objects.create(
            user=user,
            course=course,
            mode='honor',
        )
        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(
        reverse('onlinecourse:course_details', args=(course.id,))
    )


def extract_answers(request):
    submitted_answers = []

    for key in request.POST:
        if key.startswith('choice'):
            try:
                submitted_answers.append(int(request.POST[key]))
            except (ValueError, TypeError):
                continue

    return submitted_answers


@login_required
def submit(request, course_id):
    course = get_object_or_404(Course, pk=course_id)

    if request.method != 'POST':
        return redirect('onlinecourse:course_details', pk=course.id)

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course,
    )

    submission = Submission.objects.create(enrollment=enrollment)

    answer_ids = extract_answers(request)
    valid_choices = Choice.objects.filter(
        question__course=course,
        id__in=answer_ids,
    )

    submission.choices.add(*valid_choices)

    return redirect(
        'onlinecourse:show_exam_result',
        course_id=course.id,
        submission_id=submission.id,
    )


@login_required
def show_exam_result(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__user=request.user,
        enrollment__course=course,
    )

    selected_ids = list(
        submission.choices.values_list('id', flat=True)
    )

    questions = Question.objects.filter(course=course).prefetch_related(
        'choice_set'
    )

    score = 0
    possible_score = 0
    question_results = []

    for question in questions:
        possible_score += question.grade

        selected_for_question = [
            choice_id
            for choice_id in selected_ids
            if question.choice_set.filter(id=choice_id).exists()
        ]

        question_score = question.is_get_score(selected_for_question)
        score += question_score

        question_results.append({
            'question': question,
            'choices': question.choice_set.all(),
            'selected_ids': selected_for_question,
            'possible': question.grade,
            'score': question_score,
        })

    context = {
        'course': course,
        'submission': submission,
        'selected_ids': selected_ids,
        'possible': possible_score,
        'possible_score': score,
        'score': score,
        'question_results': question_results,
    }

    return render(
        request,
        'onlinecourse/exam_result_bootstrap.html',
        context,
    )
