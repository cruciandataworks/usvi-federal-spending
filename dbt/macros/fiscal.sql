{# The federal fiscal year that contains a date: FY2026 runs from 1 Oct 2025 to 30 Sep 2026. #}
{% macro fiscal_year_of(d) -%}
    (year({{ d }}) + case when month({{ d }}) >= 10 then 1 else 0 end)
{%- endmacro %}

{# The fiscal year we are in today. #}
{% macro current_fy() -%}
    {{ fiscal_year_of('current_date') }}
{%- endmacro %}

{# True for the last `recent_fys` complete fiscal years, e.g. FY2022-FY2026 during FY2027. #}
{% macro in_recent_fys(col) -%}
    ({{ col }} between {{ current_fy() }} - {{ var('recent_fys') }} and {{ current_fy() }} - 1)
{%- endmacro %}
