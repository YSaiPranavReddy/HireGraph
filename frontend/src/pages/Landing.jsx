import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@clerk/clerk-react'
import { IoFlash } from 'react-icons/io5'
import CardNav from '../components/CardNav'
import LightPillar from '../components/LightPillar'
import FlowingMenu from '../components/FlowingMenu'
import './Landing.css'

const AGENTS = [
  { icon: '🔍', title: 'JD Parser',        desc: 'Extracts required skills, experience thresholds, and responsibilities from any job description.' },
  { icon: '📄', title: 'Resume Screener',  desc: 'Processes all resumes in parallel — skills, experience, education extracted in seconds.' },
  { icon: '🏆', title: 'Ranker',           desc: 'Scores every candidate 0–100 across skills match, experience fit, and role relevance.' },
  { icon: '⚖️', title: 'Bias Checker',     desc: 'Audits the JD itself for age proxies, gender-coded language, and degree elitism.' },
  { icon: '🧠', title: 'Critique Agent',   desc: 'Gemini independently reviews the ranking. If scores contradict evidence, it loops back and corrects.' },
  { icon: '✉️', title: 'Outreach Drafter', desc: 'Writes personalized interview invites for top candidates — not templates, actual prose.' },
]

const STEPS = [
  { num: '01', title: 'Upload',  desc: 'Drop your Job Description and candidate resumes. Text or PDF — both work.' },
  { num: '02', title: 'Analyze', desc: '6 AI agents run in parallel. JD parsed, resumes screened, bias checked — all at once.' },
  { num: '03', title: 'Decide',  desc: 'Get a ranked shortlist, bias report, AI critique, and ready-to-send emails in one view.' },
]

export default function Landing() {
  const { isSignedIn } = useAuth()
  const navigate = useNavigate()

  const navItems = [
    {
      label: 'Get Started',
      bgColor: 'rgba(255, 255, 255, 0.05)',
      textColor: '#fff',
      links: [
        { label: 'Dashboard', href: '/dashboard' },
        { label: 'Register', href: '/sign-up' },
      ],
    },
    {
      label: 'Explore',
      bgColor: 'rgba(255, 255, 255, 0.05)',
      textColor: '#fff',
      links: [
        { label: 'About', href: '#about' },
        { label: 'Features', href: '#how-it-works' },
      ],
    },
    {
      label: 'Login',
      bgColor: '#ffffff',
      textColor: '#000',
      links: [
        { label: 'Sign In', href: '/sign-in' },
      ],
    },
  ];

  return (
    <div className="landing">
      <CardNav 
        logo="/hiregraph.png" 
        items={navItems}
        baseColor="rgba(30, 27, 46, 0.8)"
        menuColor="#fff"
        buttonBgColor="#fff"
        buttonTextColor="#000"
        onGetStarted={() => navigate(isSignedIn ? '/dashboard' : '/sign-up')}
        className="backdrop-blur-md"
      />

      {/* ── Hero ─────────────────────────────── */}
      <section className="hero" style={{ position: 'relative', overflow: 'hidden' }}>
        <LightPillar
          topColor="#000000"
          bottomColor="#ffc6fd"
          intensity={0.4}
          rotationSpeed={0.3}
          glowAmount={0.003}
          pillarWidth={5.2}
          pillarHeight={0.2}
          noiseIntensity={0.5}
          pillarRotation={70}
          interactive={true}
          mixBlendMode="screen"
          quality="high"
          style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 0, pointerEvents: 'none' }}
        />
        <div className="hero-glow" />
        <div className="hero-content" style={{ position: 'relative', zIndex: 10 }}>
          <h1 className="hero-title">
            Hire smarter. <span className="gradient-text">Not harder.</span>
          </h1>
          <p className="hero-subtitle">
            Not just another resume scanner. ATS tools match resumes to job descriptions — HireGraph does that along with matching candidates to your team.<br/> 6 AI agents. Zero bias.Your next best hire is in there. Find them in 2 minutes.
          </p>
          <div className="hero-actions">
            <Link to="/sign-up" className="btn btn-primary btn-lg">
              Start for free
            </Link>
            <a href="#how-it-works" className="btn btn-outline btn-lg">
              How it works
            </a>
          </div>
          <div className="hero-stats">
            <div className="stat"><span className="stat-num">6</span><span className="stat-label">AI Agents</span></div>
            <div className="stat-divider" />
            <div className="stat"><span className="stat-num"><IoFlash /></span><span className="stat-label">Parallel Processing</span></div>
            <div className="stat-divider" />
            <div className="stat"><span className="stat-num">0</span><span className="stat-label">Bias Blind Spots</span></div>
          </div>
        </div>
      </section>

      {/* ── Agents section ──────────────────────── */}
      <section className="section agents-section">
        <div className="section-inner" style={{ maxWidth: '1200px' }}>
          <div className="section-header">
            <h2 className="section-title">Six agents. One pipeline.</h2>
            <p className="section-sub">Each agent is specialized and Together they replace hours of manual work.</p>
          </div>
          <div style={{ height: '55vh', minHeight: '400px', display: 'flex', flexDirection: 'column', borderRadius: '1.5rem', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.08)' }}>
            <FlowingMenu 
                items={AGENTS.map(a => ({ text: a.title, icon: a.icon, desc: a.desc }))}
                bgColor="#0f0f11"
                marqueeBgColor="#ffffff"
                marqueeTextColor="#000000"
                textColor="#ffffff"
                borderColor="rgba(255,255,255,0.08)"
            />
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────── */}
      <section id="how-it-works" className="section steps-section">
        <div className="section-inner">
          <div className="section-header">
            <span className="badge badge-purple">How It Works</span>
            <h2 className="section-title">From JD to shortlist in 3 steps</h2>
          </div>
          <div className="steps-row">
            {STEPS.map((s, i) => (
              <div key={i} className="step-card">
                <div className="step-num">{s.num}</div>
                <h3 className="step-title">{s.title}</h3>
                <p className="step-desc">{s.desc}</p>
                {i < STEPS.length - 1 && <div className="step-arrow">→</div>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ──────────────────────────────── */}
      <section className="section cta-section">
        <div className="cta-card">
          <div className="cta-glow" />
          <h2 className="cta-title">Ready to transform your hiring?</h2>
          <p className="cta-sub">No credit card. No setup fees. Just better hiring.</p>
          <Link to="/sign-up" className="btn btn-primary btn-lg">
            Get started free →
          </Link>
        </div>
      </section>

      {/* ── Footer ───────────────────────────── */}
      <footer className="footer">
        <div className="footer-logo">
          <img src="/hiregraph.png" alt="HireGraph Logo" style={{ height: '40px', width: 'auto' }} />
        </div>
        <p className="footer-copy">Built with LangGraph · Groq · Gemini</p>
      </footer>
    </div>
  )
}
