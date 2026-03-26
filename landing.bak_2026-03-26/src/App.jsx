import { Suspense } from 'react';
import ProgressBar from './components/ui/ProgressBar';
import ScrollToTop from './components/ui/ScrollToTop';
import Header from './components/layout/Header';
import Hero from './components/sections/Hero';
import Stats from './components/sections/Stats';
import Features from './components/sections/Features';
import HowItWorks from './components/sections/HowItWorks';
import AccessMethods from './components/sections/AccessMethods';
import Deploy from './components/sections/Deploy';
import OpenSource from './components/sections/OpenSource';
import FAQ from './components/sections/FAQ';
import Contact from './components/sections/Contact';
import Footer from './components/layout/Footer';
export default function App() {
  return (
    <div className="min-h-screen relative">
      <ProgressBar />
      <Header />
      <Suspense fallback={null}>
        <main>
          <Hero />
          <Stats />
          <Features />
          <HowItWorks />
          <AccessMethods />
          <Deploy />
          <OpenSource />
          <FAQ />
          <Contact />
        </main>
      </Suspense>
      <Footer />
      <ScrollToTop />
    </div>
  );
}
