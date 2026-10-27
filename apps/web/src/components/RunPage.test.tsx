import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeEventSource, pausedView, RESULT, REVIEW, runView, stubFetch } from '../test/fakes'
import { ResultView } from './ResultView'
import { RunPage } from './RunPage'

const step = (label: string) => screen.getByText(label).closest('li')!

describe('RunPage', () => {
  beforeEach(() => FakeEventSource.install())

  it("shows the run's usage and a link to its trace", async () => {
    const usage = { llm_calls: 4, input_tokens: 11_000, output_tokens: 1_400, seconds: 83.6 }
    const trace_url = 'http://localhost:3100/project/p1/sessions/r1'
    stubFetch({ 'GET /runs/r1': () => pausedView({ usage, trace_url }) })
    render(<RunPage runId="r1" />)
    act(() => FakeEventSource.latest().emit('status', pausedView({ usage, trace_url })))

    expect(await screen.findByText(/4 model calls · 12.4K tokens · 1m 24s/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Trace' })).toHaveAttribute('href', trace_url)
  })

  it('follows a run to the review, then approves it', async () => {
    let view = runView()
    const calls = stubFetch({
      'GET /runs/r1': () => view,
      'POST /runs/r1/review': () => pausedView({ status: 'running', review: null }),
    })
    const onChange = vi.fn()
    render(<RunPage runId="r1" onChange={onChange} />)
    const source = FakeEventSource.latest()

    act(() => source.emit('status', view))
    act(() => source.emit('step', { node: 'parse_posting', elapsed: 0 }))
    expect(screen.getByText('Reading the posting…')).toBeInTheDocument()
    expect(step('Read the posting')).toHaveAttribute('data-state', 'active')

    // Once the posting is parsed the run has a title, so it's reloaded
    view = runView({
      title: 'Senior Backend Engineer',
      company: 'Northwind',
      steps: pausedView().steps.slice(0, 1),
      next_step: 'retrieve_experience',
    })
    act(() => source.emit('node', { node: 'parse_posting', elapsed: 1.5, detail: '3 requirements' }))
    act(() => source.emit('step', { node: 'retrieve_experience', elapsed: 1.5 }))
    expect(await screen.findByText('Senior Backend Engineer')).toBeInTheDocument()
    expect(within(step('Read the posting')).getByText('3 requirements · 1.5s')).toBeInTheDocument()
    expect(step('Find your evidence')).toHaveAttribute('data-state', 'active')
    expect(onChange).toHaveBeenCalled()

    // The draft shows up as it's written, then the review replaces it
    act(() => source.emit('draft', { revision: 1, summary: 'Backend engineer', bullets: [] }))
    expect(screen.getByText('Writing draft 1…')).toBeInTheDocument()
    expect(screen.getByText('Backend engineer')).toBeInTheDocument()
    act(() => source.emit('draft', { revision: 1, summary: 'Backend engineer who', bullets: ['Built a'] }))
    expect(screen.getByText('Built a')).toBeInTheDocument()

    view = pausedView()
    act(() => source.emit('review', REVIEW))
    expect(await screen.findByText('Draft 1')).toBeInTheDocument()
    expect(step('Your review')).toHaveAttribute('data-state', 'waiting')
    expect(source.closed).toBe(true)

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    expect(calls.at(-1)).toEqual({ method: 'POST', path: '/runs/r1/review', body: { action: 'approve' } })
    expect(FakeEventSource.instances).toHaveLength(2) // following the run again
    expect(screen.queryByText('Draft 1')).not.toBeInTheDocument()
  })

  it('retries a failed run', async () => {
    const failed = runView({ status: 'failed', error: '429 quota exceeded', next_step: 'match_requirements' })
    const calls = stubFetch({ 'POST /runs/r1/retry': () => runView({ next_step: 'match_requirements' }) })
    render(<RunPage runId="r1" />)

    act(() => FakeEventSource.latest().emit('status', failed))
    expect(screen.getByText('429 quota exceeded')).toBeInTheDocument()
    expect(step('Match requirements')).toHaveAttribute('data-state', 'failed')
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(calls.at(-1)).toMatchObject({ method: 'POST', path: '/runs/r1/retry' })
    expect(step('Match requirements')).toHaveAttribute('data-state', 'active')
  })

  it('shows a rejected decision and keeps the draft', async () => {
    stubFetch({
      'POST /runs/r1/review': { status: 409, body: { detail: 'The run is done, not awaiting review.' } },
    })
    render(<RunPage runId="r1" />)

    act(() => FakeEventSource.latest().emit('status', pausedView()))
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    expect(await screen.findByText('The run is done, not awaiting review.')).toBeInTheDocument()
    expect(screen.getByText('Draft 1')).toBeInTheDocument()
  })
})

describe('ResultView', () => {
  it('copies the Markdown', async () => {
    const user = userEvent.setup() // gives the page a clipboard
    render(<ResultView result={RESULT} />)

    expect(screen.getByText(/No evidence for these must-haves: Go/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Copy Markdown' }))

    expect(await navigator.clipboard.readText()).toBe(RESULT.markdown)
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })
})
