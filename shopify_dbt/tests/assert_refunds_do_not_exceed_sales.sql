-- Sanity: a line can't refund more than it sold.
select order_line_id, net_sales, refunded_amount
from {{ ref('fct_order_lines') }}
where refunded_amount > net_sales + 0.01
