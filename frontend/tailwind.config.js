/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // Pipeup typography system
        sans: [
          'Space Grotesk',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
        serif: [
          'Playfair Display',
          'Georgia',
          'serif',
        ],
        mono: [
          'JetBrains Mono',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'monospace',
        ],
      },
      colors: {
        // Pipeup color palette
        background: {
          primary: '#FAFAF9',      // Warm off-white
          secondary: '#F5F5F4',    // Soft cream
          card: '#FFFFFF',          // Pure white
        },
        dark: {
          primary: '#1C1917',       // Warm charcoal
          secondary: '#292524',     // Lighter charcoal
          tertiary: '#44403C',      // Muted dark
        },
        accent: {
          lime: '#84CC16',          // Bright lime green
          limeHover: '#65A30D',     // Darker lime
          limeLight: '#BEF264',     // Lighter lime
        },
        // Primary alias — the brand green. Maps to accent.lime.
        // Provided so existing classes like text-primary-500/600/700
        // resolve to a tuned shade for high-contrast text on the off-white
        // background.
        primary: {
          DEFAULT: '#84CC16',
          50:  '#F7FEE7',
          100: '#ECFCCB',
          200: '#D9F99D',
          300: '#BEF264',
          400: '#A3E635',
          500: '#84CC16',
          600: '#65A30D',
          700: '#4D7C0F',
          800: '#3F6212',
          900: '#365314',
        },
        muted: {
          light: '#A8A29E',         // Light gray
          medium: '#78716C',        // Medium gray
          dark: '#57534E',          // Dark gray
        },
        border: {
          light: '#E7E5E4',          // Very light border
          medium: '#D6D3D1',         // Medium border
          dark: '#A8A29E',           // Dark border
        },
        semantic: {
          success: '#16A34A',
          warning: '#CA8A04',
          danger: '#DC2626',
          info: '#2563EB',
        },
      },
      spacing: {
        '128': '32rem',
        '144': '36rem',
        '160': '40rem',
      },
      borderRadius: {
        'pipeup': '24px',
        'pipeup-lg': '32px',
        'pipeup-xl': '40px',
      },
      boxShadow: {
        'pipeup': '0 2px 8px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.02)',
        'pipeup-lg': '0 8px 30px rgba(0, 0, 0, 0.06), 0 4px 12px rgba(0, 0, 0, 0.04)',
        'pipeup-xl': '0 20px 60px rgba(0, 0, 0, 0.08), 0 8px 20px rgba(0, 0, 0, 0.06)',
        'pipeup-glow': '0 0 30px rgba(132, 204, 22, 0.10)',
      },
      transitionTimingFunction: {
        'pipeup': 'cubic-bezier(0.4, 0, 0.2, 1)',
        'pipeup-spring': 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
      transitionDuration: {
        'pipeup': '400ms',
        'pipeup-slow': '600ms',
      },
    },
  },
  plugins: [],
}
