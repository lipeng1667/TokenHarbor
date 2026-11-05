(()=>{'use strict';
  document.documentElement.classList.add('js');
  const menu=document.querySelector('.contents');
  document.querySelectorAll('.toc a').forEach(link=>link.addEventListener('click',()=>{menu.open=false;}));
  document.addEventListener('click',event=>{if(menu.open&&!menu.contains(event.target))menu.open=false;});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&menu.open){menu.open=false;menu.querySelector('summary').focus();}});
  document.querySelector('.print-button').addEventListener('click',()=>window.print());
  const chapters=[...document.querySelectorAll('.chapter')],links=[...document.querySelectorAll('.toc a')];
  let pending=false;
  function currentSection(){
    const top=document.querySelector('.masthead').getBoundingClientRect().height+36;
    let current=chapters[0];
    for(const chapter of chapters){if(chapter.getBoundingClientRect().top<=top)current=chapter;else break;}
    links.forEach(link=>{if(link.hash===`#${current.id}`)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');});
  }
  addEventListener('scroll',()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{currentSection();pending=false;});},{passive:true});
  currentSection();
})();
