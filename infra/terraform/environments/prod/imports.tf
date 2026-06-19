# ---------------------------------------------------------------------------
# Import blocks: adopt the saalr.io DNS records that already exist in the
# Route 53 zone (created out-of-band during the zero-downtime migration off
# Netlify/NS1) so the first `terraform apply` ADOPTS them instead of failing
# with "already exists".
#
# These are one-shot: remove this file after the first successful apply has
# imported them (Terraform will note they can be removed). They must also be
# removed before the Phase 2d apex cutover (when apex_on_netlify=false the
# apex/www records no longer exist for the [0] addresses to import).
#
# Zone id: Z0131776360WYD1MAXWUK
# ---------------------------------------------------------------------------

import {
  to = aws_route53_record.mx[0]
  id = "Z0131776360WYD1MAXWUK_saalr.io_MX"
}

import {
  to = aws_route53_record.txt[0]
  id = "Z0131776360WYD1MAXWUK_saalr.io_TXT"
}

import {
  to = aws_route53_record.dmarc[0]
  id = "Z0131776360WYD1MAXWUK__dmarc.saalr.io_TXT"
}

import {
  to = aws_route53_record.demo[0]
  id = "Z0131776360WYD1MAXWUK_demo.saalr.io_CNAME"
}

import {
  to = aws_route53_record.apex_netlify[0]
  id = "Z0131776360WYD1MAXWUK_saalr.io_A"
}

import {
  to = aws_route53_record.www_netlify[0]
  id = "Z0131776360WYD1MAXWUK_www.saalr.io_CNAME"
}

import {
  to = aws_route53_record.dkim["protonmail"]
  id = "Z0131776360WYD1MAXWUK_protonmail._domainkey.saalr.io_CNAME"
}

import {
  to = aws_route53_record.dkim["protonmail2"]
  id = "Z0131776360WYD1MAXWUK_protonmail2._domainkey.saalr.io_CNAME"
}

import {
  to = aws_route53_record.dkim["protonmail3"]
  id = "Z0131776360WYD1MAXWUK_protonmail3._domainkey.saalr.io_CNAME"
}
