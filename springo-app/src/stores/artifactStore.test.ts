import { describe, it, expect, beforeEach } from 'vitest'
import { useArtifactStore } from './artifactStore'
import type { ArtifactItem } from './artifactStore'

function makeArtifact(id: string, title: string): ArtifactItem {
  return { id, type: 'markdown', title, content: '# ' + title, timestamp: Date.now() }
}

describe('artifactStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    useArtifactStore.setState({
      activeArtifact: null,
      artifacts: [],
      panelOpen: false,
      sessionMap: {},
      currentSessionId: null,
    })
  })

  it('openArtifact adds to history and opens panel', () => {
    const art = makeArtifact('a1', 'Doc A')
    useArtifactStore.getState().openArtifact(art)

    const state = useArtifactStore.getState()
    expect(state.panelOpen).toBe(true)
    expect(state.activeArtifact?.id).toBe('a1')
    expect(state.artifacts).toHaveLength(1)
  })

  it('openArtifact deduplicates by id', () => {
    const art = makeArtifact('a1', 'Doc A')
    useArtifactStore.getState().openArtifact(art)
    useArtifactStore.getState().openArtifact(art)

    expect(useArtifactStore.getState().artifacts).toHaveLength(1)
  })

  it('closePanel hides panel but keeps artifacts', () => {
    const art = makeArtifact('a1', 'Doc A')
    useArtifactStore.getState().openArtifact(art)
    useArtifactStore.getState().closePanel()

    const state = useArtifactStore.getState()
    expect(state.panelOpen).toBe(false)
    expect(state.artifacts).toHaveLength(1)
    expect(state.activeArtifact?.id).toBe('a1')
  })

  describe('switchSession', () => {
    it('saves and restores state when switching A → B → A', () => {
      const { switchSession, openArtifact } = useArtifactStore.getState()

      // Enter session A
      switchSession('session-a')
      openArtifact(makeArtifact('a1', 'Report A'))
      openArtifact(makeArtifact('a2', 'Chart A'))

      // Verify session A state
      expect(useArtifactStore.getState().artifacts).toHaveLength(2)
      expect(useArtifactStore.getState().activeArtifact?.id).toBe('a2')
      expect(useArtifactStore.getState().panelOpen).toBe(true)

      // Switch to session B
      useArtifactStore.getState().switchSession('session-b')

      // Session B should be empty
      expect(useArtifactStore.getState().artifacts).toHaveLength(0)
      expect(useArtifactStore.getState().activeArtifact).toBeNull()
      expect(useArtifactStore.getState().panelOpen).toBe(false)

      // Add artifact in session B
      useArtifactStore.getState().openArtifact(makeArtifact('b1', 'Doc B'))
      expect(useArtifactStore.getState().artifacts).toHaveLength(1)

      // Switch back to session A
      useArtifactStore.getState().switchSession('session-a')

      // Session A state should be restored
      expect(useArtifactStore.getState().artifacts).toHaveLength(2)
      expect(useArtifactStore.getState().activeArtifact?.id).toBe('a2')
      expect(useArtifactStore.getState().panelOpen).toBe(true)
    })

    it('preserves session B state when switching A → B → A → B', () => {
      useArtifactStore.getState().switchSession('session-a')
      useArtifactStore.getState().openArtifact(makeArtifact('a1', 'Doc A'))

      // A → B
      useArtifactStore.getState().switchSession('session-b')
      useArtifactStore.getState().openArtifact(makeArtifact('b1', 'Doc B1'))
      useArtifactStore.getState().openArtifact(makeArtifact('b2', 'Doc B2'))

      // B → A
      useArtifactStore.getState().switchSession('session-a')
      expect(useArtifactStore.getState().activeArtifact?.id).toBe('a1')

      // A → B again
      useArtifactStore.getState().switchSession('session-b')

      // Session B should be fully restored
      expect(useArtifactStore.getState().artifacts).toHaveLength(2)
      expect(useArtifactStore.getState().activeArtifact?.id).toBe('b2')
      expect(useArtifactStore.getState().panelOpen).toBe(true)
    })

    it('preserves panel closed state', () => {
      useArtifactStore.getState().switchSession('session-a')
      useArtifactStore.getState().openArtifact(makeArtifact('a1', 'Doc A'))
      useArtifactStore.getState().closePanel()

      // A → B → A
      useArtifactStore.getState().switchSession('session-b')
      useArtifactStore.getState().switchSession('session-a')

      // Panel should still be closed
      expect(useArtifactStore.getState().panelOpen).toBe(false)
      expect(useArtifactStore.getState().artifacts).toHaveLength(1)
    })

    it('handles new session with no prior state', () => {
      useArtifactStore.getState().switchSession('session-new')

      expect(useArtifactStore.getState().artifacts).toHaveLength(0)
      expect(useArtifactStore.getState().activeArtifact).toBeNull()
      expect(useArtifactStore.getState().panelOpen).toBe(false)
    })

    it('handles null session id', () => {
      useArtifactStore.getState().switchSession('session-a')
      useArtifactStore.getState().openArtifact(makeArtifact('a1', 'Doc A'))

      // Switch to null (no session)
      useArtifactStore.getState().switchSession(null)

      expect(useArtifactStore.getState().artifacts).toHaveLength(0)
      expect(useArtifactStore.getState().panelOpen).toBe(false)

      // Switch back — session A should be restored
      useArtifactStore.getState().switchSession('session-a')
      expect(useArtifactStore.getState().artifacts).toHaveLength(1)
    })
  })
})
