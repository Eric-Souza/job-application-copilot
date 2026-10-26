import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { REVIEW } from '../test/fakes'
import { ReviewPanel } from './ReviewPanel'

function setup() {
  const onDecision = vi.fn()
  render(<ReviewPanel review={REVIEW} busy={false} onDecision={onDecision} />)
  return { user: userEvent.setup(), onDecision }
}

describe('ReviewPanel', () => {
  it('shows the draft with its grounding flags and coverage', () => {
    setup()

    expect(screen.getByText('Draft 1')).toBeInTheDocument()
    expect(screen.getByText(REVIEW.bullets[0].text)).toBeInTheDocument()
    expect(screen.getByText('Check: "80%" is not in the evidence')).toBeInTheDocument()
    const table = screen.getByRole('table', { name: 'Requirement coverage' })
    expect(table).toHaveTextContent('Kubernetes (nice to have)')
    expect(table).toHaveTextContent('Nothing on Kubernetes.')
  })

  it('approves', async () => {
    const { user, onDecision } = setup()

    await user.click(screen.getByRole('button', { name: 'Approve' }))

    expect(onDecision).toHaveBeenCalledWith({ action: 'approve' })
  })

  it('asks for changes with feedback', async () => {
    const { user, onDecision } = setup()

    await user.click(screen.getByRole('button', { name: 'Ask for changes' }))
    const redraft = screen.getByRole('button', { name: 'Redraft' })
    expect(redraft).toBeDisabled()
    await user.type(screen.getByLabelText('What should change?'), '  Shorter summary. ')
    await user.click(redraft)

    expect(onDecision).toHaveBeenCalledWith({ action: 'revise', feedback: 'Shorter summary.' })
  })

  it('sends edited and dropped bullets with their ids, and leaves an unchanged summary out', async () => {
    const { user, onDecision } = setup()

    await user.click(screen.getByRole('button', { name: 'Edit it myself' }))
    const first = screen.getAllByRole('textbox')[1]
    await user.clear(first)
    await user.type(first, 'Built a Go payments API.')
    await user.click(screen.getByRole('button', { name: 'Drop bullet 2' }))
    await user.click(screen.getByRole('button', { name: 'Save edits' }))

    expect(onDecision).toHaveBeenCalledWith({
      action: 'edit',
      bullets: [{ text: 'Built a Go payments API.', requirement_ids: ['R1'], evidence_ids: ['E1'] }],
    })
  })

  it('sends only the summary when only the summary changed', async () => {
    const { user, onDecision } = setup()

    await user.click(screen.getByRole('button', { name: 'Edit it myself' }))
    const summary = screen.getByLabelText('Summary')
    await user.clear(summary)
    await user.type(summary, 'New summary.')
    await user.click(screen.getByRole('button', { name: 'Save edits' }))

    expect(onDecision).toHaveBeenCalledWith({ action: 'edit', summary: 'New summary.' })
  })

  it('saving without changes just leaves edit mode', async () => {
    const { user, onDecision } = setup()

    await user.click(screen.getByRole('button', { name: 'Edit it myself' }))
    await user.click(screen.getByRole('button', { name: 'Save edits' }))

    expect(onDecision).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
  })

  it('needs at least one bullet', async () => {
    const { user } = setup()

    await user.click(screen.getByRole('button', { name: 'Edit it myself' }))
    await user.click(screen.getByRole('button', { name: 'Drop bullet 1' }))
    await user.click(screen.getByRole('button', { name: 'Drop bullet 2' }))

    expect(screen.getByRole('button', { name: 'Save edits' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Keep bullet 2' }))
    expect(screen.getByRole('button', { name: 'Save edits' })).toBeEnabled()
  })
})
