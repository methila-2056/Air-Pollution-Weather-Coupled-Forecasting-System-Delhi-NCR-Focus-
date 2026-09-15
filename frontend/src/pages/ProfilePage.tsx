import { BadgeCheck, Clock, Mail, ShieldCheck, User } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import PageHeader from '../components/PageHeader'

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
}

export default function ProfilePage() {
  const { user } = useAuth()
  const navigate = useNavigate()

  if (!user) {
    navigate('/login', { replace: true })
    return null
  }

  const rows = [
    { icon: User, label: 'Name', value: user.name },
    { icon: Mail, label: 'Email address', value: user.email },
    { icon: ShieldCheck, label: 'Role', value: user.role },
    { icon: BadgeCheck, label: 'Account type', value: user.id === 1 ? 'Seeded demo account' : 'Registered account' },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Profile"
        subtitle="Signed-in analyst session details"
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Profile' }]}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="card flex flex-col items-center text-center lg:col-span-1">
          <span className="flex h-20 w-20 items-center justify-center rounded-full bg-inst-700 text-2xl font-bold text-white">
            {initials(user.name)}
          </span>
          <h2 className="mt-3 text-lg font-bold text-slate-900">{user.name}</h2>
          <p className="text-sm text-slate-500">{user.role}</p>
          <span className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-green-200 bg-green-50 px-3 py-1 text-xs font-semibold text-green-700">
            <span className="h-1.5 w-1.5 rounded-full bg-green-600" aria-hidden="true" />
            Active session
          </span>
          <p className="mt-4 text-xs leading-relaxed text-slate-500">
            This demonstration portal enforces session-based access control. Data APIs
            remain accessible to operational scripts.
          </p>
        </div>

        <div className="card lg:col-span-2">
          <p className="card-header">Account details</p>
          <dl className="divide-y divide-slate-100">
            {rows.map((r) => (
              <div key={r.label} className="flex items-center gap-4 py-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-inst-50">
                  <r.icon className="h-4 w-4 text-inst-700" aria-hidden="true" />
                </span>
                <dt className="w-40 text-sm font-medium text-slate-500">{r.label}</dt>
                <dd className="flex-1 text-sm font-semibold text-slate-900">{r.value}</dd>
              </div>
            ))}
          </dl>

          <p className="card-header mt-6">Session</p>
          <p className="flex items-center gap-2 text-xs text-slate-500">
            <Clock className="h-3.5 w-3.5" aria-hidden="true" />
            Tokens are signed (HS256) and expire after your operating shift. On expiry you
            will be returned to the sign-in page.
          </p>
        </div>
      </div>
    </div>
  )
}