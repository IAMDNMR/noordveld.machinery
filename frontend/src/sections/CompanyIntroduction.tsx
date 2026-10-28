import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { FilmSlot } from '../components/media/FilmSlot'
import { films } from '../data/content'

export function CompanyIntroduction() {
  return (
    <section id="company" className="company-introduction" aria-labelledby="company-intro-title">
      <div className="container">
        <div className="company-introduction__heading">
          <p className="label">THE COMPANY BEHIND THE MACHINERY</p>
          <ArrowDownRight size={40} strokeWidth={1} aria-hidden="true" />
        </div>
        <div className="company-introduction__statement">
          <h2 id="company-intro-title">
            Different origins.
            <br />
            <span>One Noordveld.</span>
          </h2>
          <div>
            <p>
              Noordveld brings together manufacturing organizations, machines and engineering
              traditions under one name.
            </p>
            <p>Explore the equipment, the work it does and the places where it is made.</p>
            <a href="#plants">
              Meet our manufacturing network <ArrowUpRight size={18} aria-hidden="true" />
            </a>
          </div>
        </div>
        <div className="company-introduction__film">
          <FilmSlot film={films.engineering} />
          <div className="company-introduction__caption">
            <span>A closer look</span>
            <p>
              Engineering.
              <br />
              In every detail.
            </p>
          </div>
        </div>
        <nav className="company-introduction__index" aria-label="Discover Noordveld">
          <Link to="/machines">
            <span>01 / THE RANGE</span>Meet the machinery{' '}
            <ArrowUpRight aria-hidden="true" size={20} />
          </Link>
          <a href="#industries">
            <span>02 / AT WORK</span>Explore the industries{' '}
            <ArrowUpRight aria-hidden="true" size={20} />
          </a>
          <a href="#plants">
            <span>03 / OUR FOOTPRINT</span>Inside Noordveld{' '}
            <ArrowUpRight aria-hidden="true" size={20} />
          </a>
        </nav>
      </div>
    </section>
  )
}
