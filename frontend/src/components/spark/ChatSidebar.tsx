import { Fragment, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, MessageSquare, Pencil, Plus, Search, Trash2, X } from 'lucide-react'
import type { ChatEntry, ChatHistory } from './useChatHistory'

export function conversationDateGroup(updated: number, now: number) {
  const today = new Date(now)
  today.setHours(0, 0, 0, 0)
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const week = new Date(today)
  week.setDate(week.getDate() - 6)
  if (updated >= today.getTime()) return 'Today'
  if (updated >= yesterday.getTime()) return 'Yesterday'
  if (updated >= week.getTime()) return 'Previous 7 days'
  return 'Earlier'
}

export function ChatSidebar({
  history,
  busy,
  onClose,
  open,
}: {
  history: ChatHistory
  busy: boolean
  onClose: () => void
  open: boolean
}) {
  const [search, setSearch] = useState('')
  const [now] = useState(() => Date.now())
  const [editing, setEditing] = useState<ChatEntry | null>(null)
  const [title, setTitle] = useState('')
  const [deleting, setDeleting] = useState<ChatEntry | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const sidebar = useRef<HTMLElement>(null)
  useEffect(() => {
    if (open && window.matchMedia?.('(max-width: 1000px)').matches)
      sidebar.current?.querySelector<HTMLButtonElement>('button')?.focus()
  }, [open])
  useEffect(() => {
    const node = sidebar.current
    const trap = (event: KeyboardEvent) => {
      if (event.key !== 'Tab' || !open || !window.matchMedia?.('(max-width: 1000px)').matches)
        return
      const items = Array.from(
        sidebar.current?.querySelectorAll<HTMLElement>('a, button:not(:disabled), input') ?? [],
      )
      const first = items[0],
        last = items.at(-1)
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last?.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first?.focus()
      }
    }
    node?.addEventListener('keydown', trap)
    return () => node?.removeEventListener('keydown', trap)
  }, [open])
  const visible = history.chats.filter((chat) =>
    `${chat.title} ${chat.search}`.toLowerCase().includes(search.toLowerCase()),
  )
  return (
    <>
      <aside ref={sidebar} className="spark-sidebar" aria-label="Chat history">
        <div className="spark-sidebar__brand">
          <Link to="/spark">
            Spark<span>by Noordveld</span>
          </Link>
          <button type="button" onClick={onClose} aria-label="Close chat history">
            <X size={18} />
          </button>
        </div>
        <p className="spark-sidebar__description">
          Parts, machines and buying decisions. One conversation.
        </p>
        <button
          type="button"
          className="spark-new-chat"
          disabled={busy}
          onClick={() => {
            history.create()
            if (window.matchMedia?.('(max-width: 1000px)').matches) onClose()
          }}
          aria-label="New conversation"
        >
          <Plus size={18} /> New chat
        </button>
        <label className="spark-history-search">
          <Search size={16} />
          <span className="sr-only">Search conversations</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search chats"
            type="search"
          />
        </label>
        <div className="spark-history-list">
          <p className="spark-sidebar__eyebrow">Recent conversations</p>
          {!visible.length ? (
            <p className="spark-history-empty">
              {search ? 'No matching conversations.' : 'Your conversations will appear here.'}
            </p>
          ) : null}
          {visible.map((chat, index) => (
            <Fragment key={chat.id}>
              {index === 0 ||
              conversationDateGroup(visible[index - 1].updated, now) !==
                conversationDateGroup(chat.updated, now) ? (
                <h2 className="spark-history-date">{conversationDateGroup(chat.updated, now)}</h2>
              ) : null}
              <div
                className={`spark-history-item${chat.id === history.active ? ' is-active' : ''}`}
                key={chat.id}
              >
                <button
                  type="button"
                  disabled={busy}
                  aria-current={chat.id === history.active ? 'page' : undefined}
                  onClick={() => {
                    history.select(chat.id)
                    if (window.matchMedia?.('(max-width: 1000px)').matches) onClose()
                  }}
                >
                  <MessageSquare size={15} />
                  <span>{chat.title}</span>
                </button>
                <div className="spark-history-item__actions">
                  <button
                    type="button"
                    aria-label={`Rename ${chat.title}`}
                    disabled={busy}
                    onClick={() => {
                      setEditing(chat)
                      setTitle(chat.title)
                      setDeleting(null)
                      dialog.current?.showModal()
                    }}
                  >
                    <Pencil size={13} />
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${chat.title}`}
                    disabled={busy}
                    onClick={() => {
                      setDeleting(chat)
                      setEditing(null)
                      dialog.current?.showModal()
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            </Fragment>
          ))}
        </div>
        <div className="spark-sidebar__footer">
          <Link to="/spark">
            Discover Spark <ArrowUpRight size={15} />
          </Link>
          <p>
            {busy
              ? 'Stop the current request to switch chats.'
              : 'History is private to this browser tab.'}
          </p>
        </div>
      </aside>
      <dialog
        ref={dialog}
        className="spark-manage-dialog"
        aria-label={editing ? 'Rename conversation' : 'Delete conversation'}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (editing) history.rename(editing.id, title)
            if (deleting) history.remove(deleting.id)
            dialog.current?.close()
          }}
        >
          <h2>{editing ? 'Rename chat' : 'Delete this chat?'}</h2>
          {editing ? (
            <label>
              Chat title
              <input
                value={title}
                maxLength={70}
                onChange={(event) => setTitle(event.target.value)}
                required
                autoFocus
              />
            </label>
          ) : (
            <p>
              This removes “{deleting?.title}” from this tab. Business records and orders stay
              unchanged.
            </p>
          )}
          <div>
            <button type="button" onClick={() => dialog.current?.close()}>
              Cancel
            </button>
            <button type="submit" className={deleting ? 'is-destructive' : ''}>
              {editing ? 'Save name' : 'Delete chat'}
            </button>
          </div>
        </form>
      </dialog>
    </>
  )
}
