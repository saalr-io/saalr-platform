import { Hero } from '../../src/features/marketing/Hero'
import { Features } from '../../src/features/marketing/Features'
import { Tiers } from '../../src/features/marketing/Tiers'
import { Footer } from '../../src/features/marketing/Footer'
import { organizationJsonLd, softwareAppJsonLd, websiteJsonLd } from '../../src/seo/jsonld'
import { ORIGIN } from '../../src/seo/origin'

export default function Page() {
  const jsonld = [organizationJsonLd(ORIGIN), softwareAppJsonLd(ORIGIN), websiteJsonLd(ORIGIN)]
  return (
    <main>
      <Hero />
      <Features />
      <Tiers />
      <Footer />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonld) }}
      />
    </main>
  )
}
