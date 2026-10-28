import { useCallback, useEffect, useState } from 'react'

export type ChatEntry = { id: string; title: string; updated: number; search: string }
type Library = { active: string; chats: ChatEntry[] }

const load = (key: string): Library => {
  try {
    const data = JSON.parse(sessionStorage.getItem(key) ?? 'null')
    if (data && typeof data.active === 'string' && Array.isArray(data.chats))
      return {
        active: data.active,
        chats: data.chats.filter(
          (chat: ChatEntry) =>
            chat &&
            typeof chat.id === 'string' &&
            typeof chat.title === 'string' &&
            typeof chat.updated === 'number' &&
            typeof chat.search === 'string',
        ),
      }
  } catch {
    /* A blocked or damaged store must not prevent chatting. */
  }
  return { active: 'current', chats: [] }
}

export function conversationKey(identity: string, id: string) {
  const base = `noordveld-spark-session:${identity}`
  return id === 'current' ? base : `${base}:${id}`
}

/** Private, tab-local history. The server still verifies every signed conversation context. */
export function useChatHistory(identity: string) {
  const key = `noordveld-spark-history:${identity}`
  const [library, setLibrary] = useState(() => load(key))
  const [storageError, setStorageError] = useState(false)
  useEffect(() => {
    try {
      sessionStorage.setItem(key, JSON.stringify(library))
      queueMicrotask(() => setStorageError(false))
    } catch {
      queueMicrotask(() => setStorageError(true))
    }
  }, [key, library])
  const update = useCallback((id: string, question: string, search: string) => {
    if (!question) return
    setLibrary((current) => {
      const previous = current.chats.find((chat) => chat.id === id)
      if (previous?.search === search) return current
      const entry = {
        id,
        title: previous?.title ?? question.slice(0, 70),
        search,
        updated: Date.now(),
      }
      return { ...current, chats: [entry, ...current.chats.filter((chat) => chat.id !== id)] }
    })
  }, [])
  const select = (id: string) => setLibrary((current) => ({ ...current, active: id }))
  const create = (draft = '') => {
    const id = crypto.randomUUID()
    if (draft) {
      try {
        sessionStorage.setItem(`${conversationKey(identity, id)}:draft`, draft)
      } catch {
        queueMicrotask(() => setStorageError(true))
      }
    }
    select(id)
  }
  const rename = (id: string, title: string) =>
    setLibrary((current) => ({
      ...current,
      chats: current.chats.map((chat) =>
        chat.id === id ? { ...chat, title: title.trim().slice(0, 70) || chat.title } : chat,
      ),
    }))
  const remove = (id: string) => {
    // Delete only this chat's own browser snapshot; never business records or server data.
    try {
      sessionStorage.removeItem(conversationKey(identity, id))
      sessionStorage.removeItem(`${conversationKey(identity, id)}:draft`)
    } catch {
      queueMicrotask(() => setStorageError(true))
    }
    setLibrary((current) => ({
      active: current.active === id ? crypto.randomUUID() : current.active,
      chats: current.chats.filter((chat) => chat.id !== id),
    }))
  }
  return { ...library, storageError, update, select, create, rename, remove }
}

export type ChatHistory = ReturnType<typeof useChatHistory>
