import datetime

import simplejson as json
from django.conf import settings
from django.http import HttpResponse
from django.utils.encoding import force_text
from django.utils.functional import Promise
from django.views.generic import FormView

from .app_settings import SLICK_REPORTING_DEFAULT_END_DATE, SLICK_REPORTING_DEFAULT_START_DATE
from .form_factory import report_form_factory
from .generator import ReportGenerator


class SampleReportView(FormView):
    group_by = None
    columns = None

    time_series_pattern = ''
    time_series_columns = None

    date_field = 'doc_date'

    swap_sign = False

    report_generator_class = ReportGenerator

    report_model = None

    base_model = None
    limit_records = None

    queryset = None

    chart_settings = None

    crosstab_model = None
    crosstab_ids = None
    crosstab_columns = None
    crosstab_compute_reminder = True

    """
    A list of chart settings objects instructing front end on how to plot the data.
    
    """

    template_name = 'slick_reporting/simple_report.html'

    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        self.form = self.get_form(form_class)
        if self.form.is_valid():
            report_data = self.get_report_results()
            if request.is_ajax():
                return self.ajax_render_to_response(report_data)

            return self.render_to_response(self.get_context_data(report_data=report_data))

        return self.render_to_response(self.get_context_data())

    def ajax_render_to_response(self, report_data):
        return HttpResponse(self.serialize_to_json(report_data),
                            content_type="application/json")

    def serialize_to_json(self, response_data):
        """ Returns the JSON string for the compiled data object. """

        def date_handler(obj):
            if type(obj) is datetime.datetime:
                return obj.strftime('%Y-%m-%d %H:%M')
            elif hasattr(obj, 'isoformat'):
                return obj.isoformat()
            elif isinstance(obj, Promise):
                return force_text(obj)

        indent = None
        if settings.DEBUG:
            indent = 4

        return json.dumps(response_data, indent=indent, use_decimal=True, default=date_handler)

    def get_form_class(self):
        """
        Automatically instantiate a form based on details provided
        :return:
        """
        return self.form_class or report_form_factory(self.report_model, crosstab_model=self.crosstab_model,
                                                      display_compute_reminder=self.crosstab_compute_reminder)

    def get_form_kwargs(self):
        """
        Returns the keyword arguments for instantiating the form.
        """
        kwargs = {
            'initial': self.get_initial(),
            'prefix': self.get_prefix(),
        }

        if self.request.method in ('POST', 'PUT'):
            kwargs.update({
                'data': self.request.POST,
                'files': self.request.FILES,
            })
        elif self.request.method in ('GET', 'PUT'):

            # elif self.request.GET:
            kwargs.update({
                'data': self.request.GET,
                'files': self.request.FILES,
            })
        return kwargs

    def get_report_generator(self, queryset, for_print):
        q_filters, kw_filters = self.form.get_filters()
        if self.crosstab_model:
            self.crosstab_ids = self.form.get_crosstab_ids()
            self.crosstab_compute_reminder = self.form.get_crosstab_compute_reminder()

        return self.report_generator_class(self.report_model,
                                           q_filters=q_filters,
                                           kwargs_filters=kw_filters,
                                           date_field=self.date_field,
                                           main_queryset=queryset,
                                           print_flag=for_print,
                                           limit_records=self.limit_records, swap_sign=self.swap_sign,
                                           columns=self.columns,
                                           group_by=self.group_by,
                                           time_series_pattern=self.time_series_pattern,
                                           time_series_columns=self.time_series_columns,

                                           crosstab_model=self.crosstab_model,
                                           crosstab_ids=self.crosstab_ids,
                                           crosstab_columns=self.crosstab_columns,
                                           crosstab_compute_reminder=self.crosstab_compute_reminder
                                           )

    def get_columns_data(self, columns):
        """
        Hook to get the columns information to front end
        :param columns:
        :return:
        """
        # columns = report_generator.get_list_display_columns()
        data = []

        for col in columns:
            data.append({
                'name': col['name'],
                'verbose_name': col['verbose_name'],
                'visible': col.get('visible', True),
                'type': col.get('type', 'text'),
                'is_summable': col.get('is_summable'),
            })
        return data

    def get_report_results(self, for_print=False):
        """
        Gets the reports Data, and, its meta data used by datatables.net and highcharts
        :return: JsonResponse
        """

        queryset = self.get_queryset()
        report_generator = self.get_report_generator(queryset, for_print)
        data = report_generator.get_report_data()
        data = self.filter_results(data, for_print)
        data = {
            'report_slug': self.get_report_slug(),
            'data': data,
            'columns': self.get_columns_data(report_generator.get_list_display_columns()),
            'metadata': self.get_metadata(generator=report_generator),
            'chart_settings': self.get_chart_settings()
        }
        return data

    def get_metadata(self, generator):
        """
        A hook to send data about the report for front end which can later be used in charting
        :return:
        """
        time_series_columns = generator.get_time_series_parsed_columns()
        metadata = {
            'time_series_pattern': self.time_series_pattern,
            'time_series_column_names': [x['name'] for x in time_series_columns],
            'time_series_column_verbose_names': [x['verbose_name'] for x in time_series_columns]
        }
        return metadata

    def get_chart_settings(self):
        """setting the chart id.. can be better """
        output = []
        for i, x in enumerate(self.chart_settings or []):
            x['id'] = f"{x['type']}-{i}"
            if not x.get('title', False):
                x['title'] = self.report_title
            output.append(x)
        return output

    def get_queryset(self):
        return self.queryset or self.report_model.objects

    def filter_results(self, data, for_print=False):
        """
        Hook to Filter results based on computed data (like eliminate __balance__ = 0, etc)
        :param data: List of objects
        :param for_print: is print request
        :return: filtered data
        """
        return data

    @classmethod
    def get_report_slug(cls):
        return cls.__name__.lower()

    def get_initial(self):
        # todo revise why not actually displaying datetime on screen
        return {
            'start_date': SLICK_REPORTING_DEFAULT_START_DATE,
            'end_date': SLICK_REPORTING_DEFAULT_END_DATE
        }
