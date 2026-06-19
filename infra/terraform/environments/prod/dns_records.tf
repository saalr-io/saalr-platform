# ---------------------------------------------------------------------------
# saalr.io DNS records (Route 53). Mirrors the zone migrated off Netlify/NS1.
#
# Permanent records (email + demo) are always managed. Apex + www are
# TRANSITIONAL: while var.apex_on_netlify they point at the existing Netlify
# site so the nameserver move is zero-downtime. At the apex cutover (Phase 2d)
# set apex_on_netlify=false and web_domain_name=saalr.io — the web module's
# CloudFront alias then owns the apex (and these records drop out).
# ---------------------------------------------------------------------------

locals {
  dns_enabled = var.dns_zone_name != ""
  dns_zone_id = local.dns_enabled ? aws_route53_zone.primary[0].zone_id : ""
}

# --- ProtonMail email (permanent) ------------------------------------------
resource "aws_route53_record" "mx" {
  count   = local.dns_enabled ? 1 : 0
  zone_id = local.dns_zone_id
  name    = var.dns_zone_name
  type    = "MX"
  ttl     = 3600
  records = ["10 mail.protonmail.ch.", "20 mailsec.protonmail.ch."]
}

# SPF + ProtonMail domain-verification share the apex TXT RRSet.
resource "aws_route53_record" "txt" {
  count   = local.dns_enabled ? 1 : 0
  zone_id = local.dns_zone_id
  name    = var.dns_zone_name
  type    = "TXT"
  ttl     = 3600
  records = [
    "v=spf1 include:_spf.protonmail.ch ~all",
    "protonmail-verification=0f73e1236acbb34a556d02352263d1c32aff3b9b",
  ]
}

resource "aws_route53_record" "dmarc" {
  count   = local.dns_enabled ? 1 : 0
  zone_id = local.dns_zone_id
  name    = "_dmarc.${var.dns_zone_name}"
  type    = "TXT"
  ttl     = 3600
  records = ["v=DMARC1; p=quarantine"]
}

resource "aws_route53_record" "dkim" {
  for_each = local.dns_enabled ? {
    "protonmail"  = "protonmail.domainkey.d4mfbxqbw2qlfftqd2jelljxckabuwg37x6tp2ft5ri5f3qfhdb7a.domains.proton.ch."
    "protonmail2" = "protonmail2.domainkey.d4mfbxqbw2qlfftqd2jelljxckabuwg37x6tp2ft5ri5f3qfhdb7a.domains.proton.ch."
    "protonmail3" = "protonmail3.domainkey.d4mfbxqbw2qlfftqd2jelljxckabuwg37x6tp2ft5ri5f3qfhdb7a.domains.proton.ch."
  } : {}
  zone_id = local.dns_zone_id
  name    = "${each.key}._domainkey.${var.dns_zone_name}"
  type    = "CNAME"
  ttl     = 3600
  records = [each.value]
}

# --- demo subdomain (permanent; stays on Netlify) --------------------------
resource "aws_route53_record" "demo" {
  count   = local.dns_enabled ? 1 : 0
  zone_id = local.dns_zone_id
  name    = "demo.${var.dns_zone_name}"
  type    = "CNAME"
  ttl     = 3600
  records = ["saalrdemo.netlify.app."]
}

# --- apex + www: TRANSITIONAL (Netlify) until the apex cutover -------------
resource "aws_route53_record" "apex_netlify" {
  count   = local.dns_enabled && var.apex_on_netlify ? 1 : 0
  zone_id = local.dns_zone_id
  name    = var.dns_zone_name
  type    = "A"
  ttl     = 3600
  records = [var.netlify_apex_ipv4]
}

resource "aws_route53_record" "www_netlify" {
  count   = local.dns_enabled && var.apex_on_netlify && var.netlify_site_host != "" ? 1 : 0
  zone_id = local.dns_zone_id
  name    = "www.${var.dns_zone_name}"
  type    = "CNAME"
  ttl     = 3600
  records = ["${var.netlify_site_host}."]
}
