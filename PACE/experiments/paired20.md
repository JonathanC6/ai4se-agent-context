# PACE · WebWalkerQA 20 题

token 合计包括动作、摘要、向量和独立评分。动作输入单列，步数含 finish，耗时为求解与评分之和。并发运行时各题时间会重叠。

| 行号 | 类型 | 判分 | 步数 | 动作输入 token | 全部 token | 秒 | glimpse |
|---:|---|---|---:|---:|---:|---:|---:|
| 2 | 单源 | 对 | 3 | 3,535 | 9,066 | 56.4 | 0 |
| 23 | 单源 | 错 | 4 | 29,149 | 43,180 | 80.1 | 0 |
| 39 | 单源 | 对 | 3 | 4,028 | 10,835 | 61.7 | 0 |
| 80 | 单源 | 对 | 3 | 3,580 | 9,031 | 61.1 | 0 |
| 118 | 单源 | 对 | 3 | 3,209 | 9,140 | 34.1 | 0 |
| 219 | 单源 | 对 | 3 | 3,987 | 9,887 | 31.4 | 0 |
| 221 | 单源 | 错 | 11 | 33,387 | 81,268 | 135.6 | 0 |
| 262 | 单源 | 对 | 5 | 12,881 | 31,842 | 70.9 | 0 |
| 266 | 单源 | 错 | 8 | 11,475 | 31,998 | 98.5 | 0 |
| 369 | 单源 | 错 | 16 | 48,933 | 101,092 | 186.2 | 0 |
| 7 | 多源 | 对 | 8 | 18,586 | 51,080 | 88.8 | 0 |
| 11 | 多源 | 错 | 3 | 3,765 | 12,159 | 30.2 | 0 |
| 12 | 多源 | 错 | 8 | 12,263 | 33,466 | 88.5 | 0 |
| 14 | 多源 | 对 | 7 | 26,305 | 55,858 | 87.0 | 0 |
| 50 | 多源 | 错 | 7 | 26,044 | 62,051 | 77.4 | 0 |
| 76 | 多源 | 错 | 16 | 39,596 | 91,357 | 178.8 | 0 |
| 435 | 多源 | 对 | 7 | 13,772 | 37,258 | 90.1 | 0 |
| 452 | 多源 | 错 | 12 | 17,281 | 42,705 | 142.1 | 0 |
| 476 | 多源 | 对 | 5 | 9,190 | 26,513 | 60.2 | 0 |
| 477 | 多源 | 对 | 4 | 16,024 | 28,613 | 44.4 | 0 |

## 题面、输出与判分依据

### 第 2 行

When and where was the ICSE duplicate submission statement agreed upon?

**模型输出**

The ICSE Duplicate Submission Statement was agreed upon at the ICSE steering committee meeting held in Charleston, South Carolina at FSE-10 in November 2002.

**参考答案**

November 2002, Charleston, South Carolina.

**评分器说明**

Prediction correctly identifies November 2002 and Charleston, South Carolina. Additional context (steering committee meeting, FSE-10) is harmless extra detail.

### 第 23 行

What visual modeling language for complex systems was introduced in the ICSE 2002 tutorial led by Joseph Gil and others on May 21, 2002?

**模型输出**

According to the ICSE 2002 Tutorials page, the visual modeling language introduced in the tutorial led by Joseph Gil and others on May 21, 2002 (Tutorial 14: "Advanced Visual Modeling: Beyond UML") included several notations:

1. **Spider diagrams** - considerably extend Venn-diagrams for specification of OO-systems
2. **Constraint diagrams** - enhance arrow notation to describe static system invariants
3. **3D-diagrams** - show how the third dimension and VRML modeling can be used for conceptual modeling of dynamic system behavior

The tutorial's theme was "upgrading of familiar diagrams into a powerful visual language" for specification of complex systems beyond UML. The co-presenters were Joseph Gil (Technion - Israel Institute of Technology), John Howse (University of Brighton), and Stuart Kent (The University, Canterbury).

**参考答案**

Advanced Visual Modeling: Beyond UML

**评分器说明**

Prediction lists specific diagram types (Spider, Constraint, 3D) instead of identifying the overarching visual modeling language. Reference expects 'Advanced Visual Modeling: Beyond UML' as the answer to what language was introduced.

### 第 39 行

Who were the program committee chairs for the ICSE 2002 conference, and when and where was this conference held?

**模型输出**

The program committee chairs for ICSE 2002 were:
- **Michal Young** (University of Oregon)
- **Jeff Magee** (Imperial College)

The conference was held in **Orlando, Florida, USA** from **May 19-25, 2002**.

**参考答案**

The program committee chairs for the 2002 ICSE conference were Michal Young and Jeff Magee. The conference was held from May 19-25, 2002 in Orlando, Florida, USA.

**评分器说明**

All required facts present: chairs Michal Young and Jeff Magee, dates May 19-25, 2002, location Orlando, Florida, USA. Institutional affiliations are harmless extra details.

### 第 80 行

On which day was the 5K Fun Run event held during the ICSE Conference 2002?

**模型输出**

The 5K Fun Run event during the ICSE Conference 2002 was held on Thursday, May 23rd, at 6:30 AM.

**参考答案**

May 23rd

**评分器说明**

Prediction correctly states May 23rd as the date, matching the reference. Additional details (Thursday, 6:30 AM) are harmless extras and do not contradict the required fact.

### 第 118 行

Web Conference 2024的标志中的'三棵树'象征着新加坡的哪三种官方语言？

**模型输出**

根据 Web Conference 2024 官网的标志说明页面，标志中的'三棵树'象征着新加坡社会的多元文化特性，代表新加坡的三种官方语言：**华语（Chinese）、马来语（Malay）和泰米尔语（Tamil）**，此外英语作为主要工作语言。

**参考答案**

Chinese, Malay, Tamil

**评分器说明**

Prediction correctly identifies all three languages (Chinese, Malay, Tamil) with equivalent naming variants. Extra context about multiculturalism and English is harmless.

### 第 219 行

Who was the General Chair of the ICSE conference in 2002?

**模型输出**

Will Tracz from Lockheed Martin Systems Integration - Owego was the General Chair of the ICSE conference in 2002.

**参考答案**

Will Tracz

**评分器说明**

The prediction names Will Tracz, matching the reference. The added affiliation (Lockheed Martin Systems Integration - Owego) is an extra detail that does not contradict the reference.

### 第 221 行

What additional content was included during the author response period at ACL 2023 to complement the new policy?

**模型输出**

During the author response period at ACL 2023, two sections were added to the peer review policies page to complement the new policy:

1. **The types of issues that the authors can flag reviews for** - guidance on what concerns authors could raise about problematic reviews

2. **FAQ: Can I use AI writing assistants to write my review?** - clarification on the use of AI tools in the review writing process

According to the page, these sections were "added to this post after the start of ACL'23 author response for completeness and in response to community feedback." The program chairs noted they hoped "having all materials in one place would also prove useful to future chairs."

**参考答案**

After the start of ACL 2023 author response, two additional sections were included for completeness and in response to community feedback.

**评分器说明**

The reference states 'two additional sections were included' without specifying their content. The prediction correctly identifies that two sections were added and provides their specific titles, but adds details not present in the reference. Since the reference only mentions that two sections were added for completeness and community feedback without naming them, and the prediction includes specific content details, this constitutes extra information beyond what the reference requires or confirms.

### 第 262 行

What was the other workshop held on the same day as the Workshop on Software Quality at ICSE 2002?

**模型输出**

Based on the ICSE 2002 workshops page, the Workshop on Software Quality was held on Saturday, May 25th (after the conference). The other workshop held on the same day was:

**Workshop 12: Workshop on Architecting Dependable Systems** (also held Saturday, May 25th)

Additionally, Workshop 10 (Open Source Software Development) was also held on Saturday, May 25th, making it three workshops total on that date.

**参考答案**

Workshop on Architecting Dependable Systems.

**评分器说明**

Prediction correctly identifies 'Workshop on Architecting Dependable Systems' as requested, with equivalent wording to reference. Extra workshop mention is harmless additional detail.

### 第 266 行

Where and when was the ICSE 2003 Program Committee Meeting held?

**模型输出**

The ICSE 2003 Program Committee Meeting was held on **Thursday, May 23, 2002**, from **17:30-18:30** in **Crystal A-C** at the Orlando, Florida conference venue during ICSE 2002.

This information was found on the ICSE 2002 Conference Meetings page, which listed meetings scheduled during that conference week, including the ICSE 2003 PC meeting.

**参考答案**

The ICSE 2003 Program Committee Meeting was held in Room Crystal A-C from 17:30 to 18:30.

**评分器说明**

Prediction adds contradictory date (May 23, 2002) and location details (Orlando, Florida, ICSE 2002) not in reference. Reference only specifies room and time.

### 第 369 行

What types of proposals had submission deadlines between September 10, 2001, and January 6, 2002?

**模型输出**

达到运行上限，未提交答案。

**参考答案**

Full Paper, Panel Proposals, State of the Art Proposals, Tutorial Proposals, Workshop Proposals, Poster and Demo Proposals.

**评分器说明**

No final answer within the episode limits.

### 第 7 行

Which tutorial at ICSE 2002 focused on the challenges of building web application systems, and what was the primary submission category emphasized by the ICSE for software engineering practitioners?

**模型输出**

Based on the ICSE 2002 conference materials:

**Tutorial on Web Applications:**
Tutorial 5, "Meeting the Challenges of Web Application Development: The Web Engineering Approach" by San Murugesan and Yogesh Deshpande from the University of Western Sydney, focused on the challenges of building web application systems. This full-day tutorial held on Monday, May 20th, addressed issues of scalability, maintainability, usability, testing, quality assurance, and Web project management specific to Web development.

**Primary Submission Category for Practitioners:**
The primary submission category emphasized for software engineering practitioners was "Industrial Participation and Sponsorship," which was designed "to provide opportunities for participation by software practitioners."

**参考答案**

Tutorial 5 ('Meeting the Challenges of Web Application Development: The Web Engineering Approach') focused on building web application systems. The primary submission category emphasized by ICSE for software engineering practitioners was 'To provide opportunities for participation by software practitioners.'

**评分器说明**

Both parts are accurate. Tutorial 5 correctly identified with appropriate title. The submission category phrase 'to provide opportunities for participation by software practitioners' is present in the prediction, though labeled under 'Industrial Participation and Sponsorship' rather than as a standalone category name—this is a harmless organizational difference that doesn't contradict the core fact requested.

### 第 11 行

Which scholars presented the IMPACT project on safety-critical systems and software inspections, reviews, and walkthroughs at the ICSE 2002 conference?

**模型输出**

The scholars who presented the IMPACT project on software inspections, reviews, and walkthroughs at ICSE 2002 were:

**Session Chairs:**
- Oliver Laitenberger (Fraunhofer Institute for Experimental Software Engineering)
- Dieter Rombach (Fraunhofer Institute for Experimental Software Engineering)

**Contributors:**
- Marcus Ciolkowski (University of Kaiserslautern and Fraunhofer Institute for Experimental Software Engineering)
- Oliver Laitenberger (Fraunhofer Institute for Experimental Software Engineering)
- Dieter Rombach (Fraunhofer Institute for Experimental Software Engineering)
- Forrest Shull (Fraunhofer Center for Experimental Software Engineering)
- Dewayne Perry (University of Texas, Austin)

This presentation was part of session S7.3 titled "Software Inspections, Reviews & Walkthroughs" and focused on quality-enhancing activities in safety-critical systems through early defect detection.

**参考答案**

The IMPACT presentations at ICSE 2002 were headed by John Knight on safety-critical systems and Oliver Laitenberger on software inspections, reviews, and walkthroughs.

**评分器说明**

Prediction omits John Knight, who headed the safety-critical systems presentation according to the reference. Prediction also conflates the two separate IMPACT presentations into one session.

### 第 12 行

What was the specific schedule for the social event held on the evening after the ACL 2023 best paper awards ceremony?

**模型输出**

The social event held on the evening after the ACL 2023 best paper awards ceremony was scheduled for **Tuesday, July 11th, from 6:30 PM to 10:00 PM** (18:30-22:00) at Steam Whistle Brewing / Canada's Premium Beer. A name badge was required for access.

The best paper awards ceremony took place on Monday, July 10th from 4:00 PM to 5:30 PM (16:00-17:30), making the social event the following evening.

**参考答案**

The social event was scheduled from 7:00 PM to 10:30 PM on July 11th.

**评分器说明**

Time mismatch: prediction states 6:30 PM to 10:00 PM, reference states 7:00 PM to 10:30 PM.

### 第 14 行

During The Web Conference 2024, which keynote speaker is addressing the challenges posed by AI deepfakes, and on what thematic special day of the conference does the discussion on Large Language Models (LLMs) take place?

**模型输出**

Based on the WWW 2024 conference website:

**Keynote Speaker on AI Deepfakes:** Jeannie Marie Paterson addresses the challenges posed by AI deepfakes, examining ethical, legal, and technical challenges in balancing safety, trust, and free speech.

**LLM Discussion Day:** Large Language Model Day takes place on **May 14, 2024**. This dedicated full-day event focuses on recent progress of foundational LLMs and building trustworthy LLMs, addressing challenges including fairness, safety, privacy preservation, explainability, and controllability.

**参考答案**

Jeannie Marie Paterson addresses AI deepfakes on May 17, 2024. Large Language Model Day is on May 14, 2024.

**评分器说明**

Both facts are present: Jeannie Marie Paterson addresses AI deepfakes, and LLM Day is May 14, 2024. The prediction includes additional context but no contradictions.

### 第 50 行

Which specific theme day does the tutorial schedule overlap with at The Web Conference 2024?

**模型输出**

The tutorial schedule overlaps with two theme days at The Web Conference 2024:

1. **Monday, May 13, 2024** - Tutorials overlap with **Online Trust & Safety Day**
2. **Tuesday, May 14, 2024** - Tutorials overlap with both **Large Language Model Day** and **Health Day**

All three special theme days run concurrently with the tutorial sessions (10 tutorials on Monday, 10 on Tuesday).

**参考答案**

Online Trust & Safety Day

**评分器说明**

Prediction lists three theme days (Online Trust & Safety Day, Large Language Model Day, Health Day) when the reference specifies only one: Online Trust & Safety Day. The extra information contradicts the 'specific' singular form in the question.

### 第 76 行

What are the submission deadlines for technical papers and the doctoral symposium at the ICSE 2002 conference?

**模型输出**

达到运行上限，未提交答案。

**参考答案**

The technical paper submission deadline was September 25, 2001, and the doctoral symposium submission deadline was January 6, 2002.

**评分器说明**

No final answer within the episode limits.

### 第 435 行

In ACL 2023, who are the Tutorial Chairs and Main Conference Chairs?

**模型输出**

Based on the ACL 2023 Organizing Committee page:

**Tutorial Chairs:**
- Yun-Nung (Vivian) Chen, National Taiwan University (Taiwan)
- Margot Mieskes, University of Applied Sciences, Darmstadt (Germany)
- Siva Reddy, McGill University and Mila (Canada)

**Main Conference Chairs (Program Chairs):**
- Jordan Boyd-Graber, University of Maryland (USA)
- Naoaki Okazaki, Tokyo Institute of Technology (Japan)
- Anna Rogers, IT University of Copenhagen (Denmark)

**参考答案**

Tutorial Chairs: Yun-Nung (Vivian) Chen, Margot Mieskes, Siva Reddy; Main Conference Chairs: Jordan Lee Boyd-Graber, Naoaki Okazaki, Anna Rogers

**评分器说明**

All requested names are present and correct. Affiliations and country details are harmless additions.

### 第 452 行

What were the exact dates and the General Chair for the ICSE conference in 2004?

**模型输出**

Based on the ICSE 2004 website:

**Dates:** May 23-28, 2004 (held at EICC, Edinburgh, Scotland, UK)

**General Chair:** Not available on the website. The main conference page and other accessible pages do not list the organizing committee or General Chair information.

**参考答案**

The ICSE 2004 conference was held from May 23 to 28, and the General Chair was Anthony Finkelstein.

**评分器说明**

Prediction provides correct dates (May 23-28, 2004) but claims General Chair information is not available, while reference specifies Anthony Finkelstein as General Chair. Missing required fact.

### 第 476 行

What is the deadline for applying for the subsidies offered for travel and accommodation for financially constrained individuals intending to attend workshops at ACL 2023, and when are these workshops scheduled?

**模型输出**

Based on the ACL 2023 website:

**Subsidy Application Deadline:** May 31, 2023 (11:59 PM UTC-12)

**Workshop Dates:** July 13-14, 2023 (Thursday-Friday), with one workshop (Queer in AI) on July 9 (Sunday)

The Diversity & Inclusion subsidies cover registration waivers, travel and accommodation support, and other expenses. Applicants presenting at workshops associated with ACL are given preference in the selection process.

**参考答案**

The deadline to apply for subsidies is May 31, 2023. The workshops are scheduled for July 13-14, 2023.

**评分器说明**

Prediction correctly states the May 31, 2023 deadline and July 13-14, 2023 workshop dates. The additional details about UTC-12 timezone, one workshop on July 9, and subsidy preferences are extra information but not contradictory.

### 第 477 行

At ACL 2023, which dates are the workshops scheduled for and what is the deadline for applying for travel and accommodation subsidies?

**模型输出**

Workshops at ACL 2023 are scheduled for July 13-14, 2023, according to the Conference Schedule on the homepage (https://2023.aclweb.org/). The Diversity and Inclusion subsidies page (https://2023.aclweb.org/calls/subsidies/) says to apply for subsidies before May 31, 2023, and lists May 31, 2023 as the application deadline. Travel and accommodation subsidies fall under that program. Deadlines use 11:59 PM UTC-12:00 (anywhere on Earth). I did not read the rest of the subsidies page past the first 4,200 characters, so I have not checked whether the travel section sets a separate deadline.

**参考答案**

Workshops at ACL 2023 are scheduled for July 13-14, 2023. The deadline to apply for travel and accommodation subsidies is May 31, 2023.

**评分器说明**

Prediction correctly states workshops are July 13-14, 2023 and the subsidy deadline is May 31, 2023. Extra details about UTC-12:00 and character limits are harmless and do not contradict the reference.

