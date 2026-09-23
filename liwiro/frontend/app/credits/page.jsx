import Link from "next/link"
import { Globe } from "lucide-react"

import { WorkspaceLayout } from "@/components/ide/workspace-layout"

const academicCredits = [
  {
    name: "Dr. Nilkanta Das",
    relationship: "Project Supervisor, KIIT University",
    contributionType: "Academic Guidance",
    note: "For supervision, direction, and steady academic guidance throughout the final project journey.",
  },
]

const assetCredits = [
  {
    name: "Maria Tyutina",
    relationship: "Pexels Photographer",
    contributionType: "Media Asset Attribution",
    note: "For the rabbit photo used in the MediaCloud demo media bundle as kalulu-0.jpg.",
    links: [
      {
        label: "Pexels Photo",
        href: "https://www.pexels.com/photo/photo-of-black-rabbit-1228439/",
        icon: Globe,
      },
    ],
  },
  {
    name: "Pixabay",
    relationship: "Pexels Contributor",
    contributionType: "Media Asset Attribution",
    note: "For the rabbit photo used in the MediaCloud demo media bundle as kalulu-1.jpg.",
    links: [
      {
        label: "Pexels Photo",
        href: "https://www.pexels.com/photo/white-and-brown-rabbit-on-green-grass-field-372166/",
        icon: Globe,
      },
    ],
  },
  {
    name: "Nicky Pe",
    relationship: "Pexels Video Creator",
    contributionType: "Media Asset Attribution",
    note: "For the hare video used in the MediaCloud demo media bundle as ba_kalulu.mp4.",
    links: [
      {
        label: "Pexels Video",
        href: "https://www.pexels.com/video/hares-in-a-grass-field-16572381/",
        icon: Globe,
      },
    ],
  },
  {
    name: "Ludovic Riffault",
    relationship: "The Noun Project Contributor",
    contributionType: "Logo Attribution",
    note: "For the original \"Hare\" icon that the Liwiro icon/logo \"Kalulu\" was adapted from, licensed under CC BY 3.0 via The Noun Project.",
    links: [
      {
        label: "Noun Project",
        href: "https://thenounproject.com/icon/hare-210728/",
        icon: Globe,
      },
    ],
  },
]

function sortCreditsByName(rows) {
  return [...rows].sort((left, right) => left.name.localeCompare(right.name, undefined, { sensitivity: "base" }))
}

function CreditRow({ name, relationship, contributionType, links }) {
  return (
    <article className="rounded-[1.35rem] border border-white/10 bg-white/5 p-5 shadow-[0_18px_38px_rgba(2,6,23,0.2)]">
      <div className="min-w-0">
        <h3 className="text-xl font-bold tracking-tight text-white md:text-2xl">{name}</h3>
        <p className="mt-1 text-sm font-medium text-sky-200">{relationship}</p>
        {Array.isArray(links) && links.length > 0 ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {links.map((entry) => {
              const Icon = entry.icon
              return (
                <Link
                  key={entry.label}
                  href={entry.href}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-100 transition hover:border-sky-300/35 hover:bg-sky-400/10 hover:text-sky-100"
                >
                  {Icon ? <Icon className="h-3.5 w-3.5" /> : null}
                  <span>{entry.label}</span>
                </Link>
              )
            })}
          </div>
        ) : null}
      </div>
      <p className="mt-3 text-sm font-medium text-sky-200">{contributionType}</p>
    </article>
  )
}

function CreditSection({ title, description, rows }) {
  const sortedRows = sortCreditsByName(rows)

  return (
    <section className="space-y-4">
      <div>
        <p className="app-stat-label">{title}</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">{title}</h2>
        <p className="mt-2 text-sm text-slate-400">{description}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {sortedRows.map((row) => (
          <CreditRow key={row.name} {...row} />
        ))}
      </div>
    </section>
  )
}

function SpecialThanksSection() {
  return (
    <section className="space-y-4">
      <div>
        <p className="app-stat-label">Special Thanks</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">Special Thanks</h2>
      </div>
      <div className="rounded-[1.35rem] border border-white/10 bg-white/5 p-5 shadow-[0_18px_38px_rgba(2,6,23,0.2)]">
        <p className="text-sm leading-7 text-slate-300">
          Special thanks to family and friends whose care, encouragement, patience, company, and steady belief made the
          long process lighter and kept the work moving forward with perspective and strength.
        </p>
      </div>
    </section>
  )
}

export default function CreditsPage() {
  return (
    <WorkspaceLayout
      eyebrow="Credits"
      title="Credits"
      description="Thanks to everyone who supported Liwiro."
      topActions={
        <div className="flex flex-wrap gap-2">
          <Link href="/wiki" className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 hover:bg-white/10">
            Open Manual
          </Link>
          <Link href="/license" className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 hover:bg-white/10">
            View License
          </Link>
        </div>
      }
      systemTitle="Thanks"
      systemDescription="People and creators who supported this project."
      editorTitle="Credits"
      editorDescription="Acknowledgements and attributions."
      systemPanel={
        <div className="space-y-4">
          <div className="rounded-[1.35rem] border border-sky-400/20 bg-sky-400/[0.08] p-5">
            <p className="text-sm text-slate-200">Thank you for the guidance, testing, support, and source work behind Liwiro.</p>
          </div>

        </div>
      }
      editorPanel={
        <div className="space-y-8">
          <CreditSection
            title="Academic Guidance"
            description="Academic support."
            rows={academicCredits}
          />

          <CreditSection
            title="Third-Party Assets"
            description="Media and logo attribution."
            rows={assetCredits}
          />

          <SpecialThanksSection />
        </div>
      }
    />
  )
}
