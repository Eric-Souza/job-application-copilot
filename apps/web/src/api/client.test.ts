import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeEventSource, REVIEW, runView, stubFetch } from '../test/fakes'
import { api, ApiError, followRun } from './client'

describe('followRun', () => {
  beforeEach(() => FakeEventSource.install())

  it('passes events on and closes when the run pauses', () => {
    const handlers = { status: vi.fn(), node: vi.fn(), review: vi.fn() }
    followRun('r1', handlers)
    const source = FakeEventSource.latest()

    expect(source.url).toBe('/api/runs/r1/events')
    source.emit('status', runView())
    source.emit('node', { node: 'parse_posting', elapsed: 1, detail: '3 requirements' })
    expect(source.closed).toBe(false)
    source.emit('review', REVIEW)

    expect(handlers.status).toHaveBeenCalledWith(runView())
    expect(handlers.node).toHaveBeenCalledWith({
      node: 'parse_posting',
      elapsed: 1,
      detail: '3 requirements',
    })
    expect(handlers.review).toHaveBeenCalledWith(REVIEW)
    expect(source.closed).toBe(true) // or EventSource would reconnect when the server ends the stream
  })

  it('closes right away for a run that is not running', () => {
    followRun('r1', {})
    FakeEventSource.latest().emit('status', runView({ status: 'done' }))

    expect(FakeEventSource.latest().closed).toBe(true)
  })

  it("tells the run's error apart from a dropped connection", () => {
    const error = vi.fn()
    followRun('r1', { error })
    const source = FakeEventSource.latest()

    source.drop()
    expect(error).not.toHaveBeenCalled()
    expect(source.closed).toBe(false) // left to reconnect

    source.emit('error', { message: '429 quota' })
    expect(error).toHaveBeenCalledWith({ message: '429 quota' })
    expect(source.closed).toBe(true)
  })
})

describe('api errors', () => {
  it("uses the API's message", async () => {
    stubFetch({
      'POST /runs/r1/review': { status: 409, body: { detail: 'The run is done, not awaiting review.' } },
    })

    await expect(api.review('r1', { action: 'approve' })).rejects.toThrow(
      'The run is done, not awaiting review.',
    )
  })

  it('joins validation errors', async () => {
    const detail = [{ msg: 'Value error, revise needs feedback' }]
    stubFetch({ 'POST /runs/r1/review': { status: 422, body: { detail } } })

    await expect(api.review('r1', { action: 'revise', feedback: '' })).rejects.toThrow(
      /^revise needs feedback$/,
    )
  })

  it('says when the API is down', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const error = await api.listRuns().catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.message).toMatch(/Could not reach the API/)
  })
})
