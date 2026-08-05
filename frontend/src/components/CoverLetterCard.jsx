import React, { useState } from 'react'
import Card from './Card'
import Button from './Button'

const CoverLetterCard = ({ coverLetter }) => {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(coverLetter.content)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      // Surface inline via the same button so the user sees feedback.
      setCopied(false)
    }
  }

  const handleDownload = () => {
    try {
      const blob = new Blob([coverLetter.content], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const safeName = (coverLetter.company || 'cover-letter')
        .replace(/[^a-z0-9]+/gi, '-')
        .replace(/^-+|-+$/g, '')
        .toLowerCase() || 'cover-letter'
      const a = document.createElement('a')
      a.href = url
      a.download = `cover-letter-${safeName}.txt`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      // Silent failure — download is a non-critical action.
    }
  }

  return (
    <Card>
      <div className="space-y-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
              AI Generated Cover Letter
            </p>
            <h3 className="mt-1 text-xl font-bold text-dark-primary">
              For {coverLetter.company}
            </h3>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="small" onClick={handleCopy} ariaLabel="Copy cover letter to clipboard">
              {copied ? 'Copied!' : 'Copy to Clipboard'}
            </Button>
            <Button size="small" onClick={handleDownload} ariaLabel="Download cover letter as text file">
              Download .txt
            </Button>
          </div>
        </div>

        <div className="rounded-pipeup border border-border-medium bg-background-secondary p-6">
          <p className="whitespace-pre-wrap font-sans text-sm font-medium leading-7 text-dark-primary">
            {coverLetter.content}
          </p>
        </div>
      </div>
    </Card>
  )
}

export default CoverLetterCard