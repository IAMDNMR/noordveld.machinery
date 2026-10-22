import {
  Boxes,
  Building2,
  CalendarDays,
  CheckCircle2,
  ContactRound,
  Database,
  ClipboardCheck,
  ClipboardList,
  CreditCard,
  FileCheck2,
  FileText,
  GitBranch,
  MapPin,
  Package,
  PackageCheck,
  Search,
  Send,
  ShieldCheck,
  Truck,
  UserRoundCheck,
  Wrench,
  XCircle,
} from 'lucide-react'

/** Choose by task meaning first, then by process kind. Shared by navigation and page headings. */
export function taskIcon(label: string, kind?: string, outcome?: string | null) {
  const text = label.toLowerCase()
  if (/cancel|reject|decline/.test(text)) return XCircle
  if (/proof|pod\b/.test(text)) return FileCheck2
  if (/tracking|track\b/.test(text)) return MapPin
  if (/assign/.test(text)) return /carrier|vehicle/.test(text) ? Truck : UserRoundCheck
  if (/dispatch|shipping|ship\b|transport/.test(text) && !/plan/.test(text)) return Truck
  if (/approv|decide|review|inspect/.test(text)) return ShieldCheck
  if (/resolv|exception|shortage|overload|reconcile/.test(text)) return GitBranch
  if (/payment|invoice|billing/.test(text)) return CreditCard
  if (/plan|schedule|leave|visit/.test(text)) return CalendarDays
  if (/receive|receipt|handoff|hand off|delivered/.test(text)) return PackageCheck
  if (/pack|pick|stock|goods/.test(text)) return Package
  if (/repair|rework|carry out|maintenance/.test(text)) return Wrench
  if (/find|search|qualify/.test(text)) return Search
  if (/submit|publish|issue/.test(text)) return Send
  if (/document|contract|proposal|quote/.test(text)) return FileText
  if (kind === 'end') return outcome === 'success' ? CheckCircle2 : XCircle
  if (kind === 'exception') return GitBranch
  if (kind === 'approval' || kind === 'review') return ClipboardCheck
  return ClipboardList
}

export function entityIcon(name: string) {
  const text = name.toLowerCase()
  if (/customer|employee|contact/.test(text)) return ContactRound
  if (/supplier|dealer|company/.test(text)) return Building2
  if (/carrier|vehicle|shipment|transport/.test(text)) return Truck
  if (/location|warehouse|depot/.test(text)) return MapPin
  if (/stock|inventory/.test(text)) return Boxes
  if (/item|part|pick|pack/.test(text)) return Package
  if (/invoice|payment/.test(text)) return CreditCard
  if (/order|request|claim/.test(text)) return FileText
  if (/machine|work order/.test(text)) return Wrench
  return Database
}
