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

# --- Clerk production instance (auth on saalr.io) --------------------------
# Frontend API, account portal, and email/DKIM CNAMEs for the Clerk prod
# instance. Required before AUTH_PROVIDER=clerk works (web Clerk init + API
# JWKS fetch both hit clerk.saalr.io). Permanent.
locals {
  clerk_cnames = local.dns_enabled ? {
    "clerk"           = "frontend-api.clerk.services."
    "accounts"        = "accounts.clerk.services."
    "clkmail"         = "mail.86c9b2fq990s.clerk.services."
    "clk._domainkey"  = "dkim1.86c9b2fq990s.clerk.services."
    "clk2._domainkey" = "dkim2.86c9b2fq990s.clerk.services."
  } : {}
}

resource "aws_route53_record" "clerk" {
  for_each = local.clerk_cnames
  zone_id  = local.dns_zone_id
  name     = "${each.key}.${var.dns_zone_name}"
  type     = "CNAME"
  ttl      = 3600
  records  = [each.value]
}

# apex (saalr.io) + www now point at CloudFront via the web module
# (module.web aws_route53_record.web_alias / www_alias, with allow_overwrite).
# The transitional Netlify pointers were removed at the go-live cutover.
