# DAG-PACE · WebWalkerQA 20 题

token 合计包括动作、摘要、向量和独立评分。动作输入单列，步数含 finish，耗时为求解与评分之和。并发运行时各题时间会重叠。

| 行号 | 类型 | 判分 | 步数 | 动作输入 token | 全部 token | 秒 | glimpse |
|---:|---|---|---:|---:|---:|---:|---:|
| 2 | 单源 | 对 | 3 | 3,619 | 9,215 | 46.6 | 0 |
| 23 | 单源 | 对 | 3 | 4,135 | 11,248 | 54.7 | 0 |
| 39 | 单源 | 对 | 3 | 4,412 | 11,301 | 53.5 | 0 |
| 80 | 单源 | 对 | 3 | 3,986 | 9,742 | 48.8 | 0 |
| 118 | 单源 | 对 | 3 | 4,154 | 10,507 | 33.3 | 0 |
| 219 | 单源 | 对 | 3 | 4,383 | 10,809 | 37.5 | 0 |
| 221 | 单源 | 错 | 7 | 20,964 | 49,863 | 88.0 | 0 |
| 262 | 单源 | 错 | 7 | 22,188 | 59,546 | 90.1 | 0 |
| 266 | 单源 | 错 | 16 | 56,805 | 110,802 | 205.9 | 0 |
| 369 | 单源 | 错 | 16 | 62,881 | 122,415 | 199.3 | 0 |
| 7 | 多源 | 对 | 6 | 14,864 | 36,684 | 76.2 | 0 |
| 11 | 多源 | 错 | 3 | 4,131 | 12,651 | 29.8 | 0 |
| 12 | 多源 | 错 | 4 | 7,525 | 23,023 | 51.0 | 0 |
| 14 | 多源 | 对 | 6 | 17,195 | 49,892 | 66.5 | 0 |
| 50 | 多源 | 对 | 6 | 27,420 | 60,893 | 67.1 | 0 |
| 76 | 多源 | 错 | 8 | 38,145 | 62,412 | 93.5 | 0 |
| 435 | 多源 | 对 | 6 | 12,233 | 34,661 | 79.7 | 0 |
| 452 | 多源 | 错 | 13 | 29,273 | 56,644 | 147.1 | 0 |
| 476 | 多源 | 对 | 6 | 15,891 | 47,748 | 72.6 | 0 |
| 477 | 多源 | 对 | 5 | 11,632 | 30,755 | 58.6 | 0 |

## 题面、输出与判分依据

### 第 2 行

When and where was the ICSE duplicate submission statement agreed upon?

**模型输出**

The ICSE duplicate submission statement was agreed to at the ICSE steering committee meeting in Charleston, South Carolina, held at FSE-10 in November 2002 (source: https://www.icse-conferences.org/duplicate.html). The page does not give a specific day.

**参考答案**

November 2002, Charleston, South Carolina.

**评分器说明**

The prediction gives both requested facts: November 2002 and Charleston, South Carolina. The added details (FSE-10, the steering committee meeting, and the note about no specific day) do not contradict the reference.

### 第 23 行

What visual modeling language for complex systems was introduced in the ICSE 2002 tutorial led by Joseph Gil and others on May 21, 2002?

**模型输出**

Based on the ICSE 2002 tutorials page, the visual modeling language introduced in the tutorial "Advanced Visual Modeling: Beyond UML" led by Joseph Gil (along with John Howse and Stuart Kent) on the morning of May 21, 2002, was **Spider diagrams**.

The tutorial description states that Spider diagrams "considerably extend Venn-diagrams to the specification of OO-systems" and translate familiar OO concepts into set theoretical terms. The tutorial also covered constraint diagrams and 3D-diagrams as part of a vision for visual modeling beyond UML for complex systems.

**参考答案**

Advanced Visual Modeling: Beyond UML

**评分器说明**

The reference names the tutorial "Advanced Visual Modeling: Beyond UML", and the prediction states this title exactly. The prediction's added claim that Spider diagrams were the language is not contradicted by the reference, so it counts as extra detail. The question asks for a language, but the reference gives the tutorial title, so the grade follows the reference.

### 第 39 行

Who were the program committee chairs for the ICSE 2002 conference, and when and where was this conference held?

**模型输出**

For ICSE 2002:

**Program Committee Chairs:**
- Michal Young (University of Oregon)
- Jeff Magee (Imperial College)

**Conference Details:**
- **When:** May 19-25, 2002
- **Where:** Orlando, Florida, USA

**参考答案**

The program committee chairs for the 2002 ICSE conference were Michal Young and Jeff Magee. The conference was held from May 19-25, 2002 in Orlando, Florida, USA.

**评分器说明**

All required facts match: chairs are Michal Young and Jeff Magee, dates are May 19-25, 2002, location is Orlando, Florida, USA. Affiliations are harmless extra details.

### 第 80 行

On which day was the 5K Fun Run event held during the ICSE Conference 2002?

**模型输出**

The 5K Fun Run event during the ICSE Conference 2002 was held on Thursday, May 23rd at 6:30 AM.

**参考答案**

May 23rd

**评分器说明**

Prediction correctly identifies May 23rd as the date, with harmless additional details about day of week and time.

### 第 118 行

Web Conference 2024的标志中的'三棵树'象征着新加坡的哪三种官方语言？

**模型输出**

Web Conference 2024标志中的'三棵树'象征着新加坡的三种官方语言：华语（Chinese）、马来语（Malay）和泰米尔语（Tamil）。此外，英语作为主要工作语言。

**参考答案**

Chinese, Malay, Tamil

**评分器说明**

Prediction correctly identifies all three languages (Chinese, Malay, Tamil). The extra detail about English as a working language is harmless additional context.

### 第 219 行

Who was the General Chair of the ICSE conference in 2002?

**模型输出**

Will Tracz from Lockheed Martin Systems Integration - Owego was the General Chair of the ICSE conference in 2002.

**参考答案**

Will Tracz

**评分器说明**

The prediction names Will Tracz as General Chair, matching the reference. The added affiliation (Lockheed Martin Systems Integration - Owego) is an extra detail that does not contradict the reference.

### 第 221 行

What additional content was included during the author response period at ACL 2023 to complement the new policy?

**模型输出**

Two sections were added to the ACL 2023 Peer Review Policies page after the start of the author response period:

1. **"The types of issues that the authors can flag reviews for"** - This section outlined specific categories of review problems (A through J) that authors could report to chairs, such as unspecific reviews, unprofessional tone, scores not matching review text, and missing expertise.

2. **"FAQ: Can I use AI writing assistants to write my review?"** - This section addressed the use of AI tools in review writing, noting that while paraphrasing assistance could be reasonable, the use of non-privacy-friendly solutions like ChatGPT was highly discouraged due to confidentiality concerns.

According to the note on the page, these sections were added "for completeness and in response to community feedback" with the goal of having all materials in one place for future chairs.

**参考答案**

After the start of ACL 2023 author response, two additional sections were included for completeness and in response to community feedback.

**评分器说明**

Prediction provides specific section titles and detailed content, but reference only states 'two additional sections' without specifying what they were. The prediction adds facts not present in the reference.

### 第 262 行

What was the other workshop held on the same day as the Workshop on Software Quality at ICSE 2002?

**模型输出**

Based on the ICSE 2002 workshops page, three workshops were held on Saturday May 25th, 2002:

1. Workshop 10: 2nd Workshop on Open Source Software Engineering
2. Workshop 11: Workshop on Software Quality
3. Workshop 12: Workshop on Architecting Dependable Systems

The other workshops held on the same day as the Workshop on Software Quality were the **2nd Workshop on Open Source Software Engineering** and the **Workshop on Architecting Dependable Systems**.

**参考答案**

Workshop on Architecting Dependable Systems.

**评分器说明**

Prediction lists two workshops instead of identifying the single other workshop requested. Reference expects 'Workshop on Architecting Dependable Systems' only.

### 第 266 行

Where and when was the ICSE 2003 Program Committee Meeting held?

**模型输出**

达到运行上限，未提交答案。

**参考答案**

The ICSE 2003 Program Committee Meeting was held in Room Crystal A-C from 17:30 to 18:30.

**评分器说明**

No final answer within the episode limits.

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

**Tutorial 5** at ICSE 2002 focused on the challenges of building web application systems: "Meeting the Challenges of Web Application Development: The Web Engineering Approach" by San Murugesan and Yogesh Deshpande from the University of Western Sydney. This full-day tutorial (held Monday, May 20th) addressed the complexity of web application development, discussing issues like scalability, maintainability, usability, testing, and quality assurance specific to web development.

The primary submission category emphasized for software engineering practitioners was **Industrial Participation and Sponsorship**, which aimed "To provide opportunities for participation by software practitioners."

**参考答案**

Tutorial 5 ('Meeting the Challenges of Web Application Development: The Web Engineering Approach') focused on building web application systems. The primary submission category emphasized by ICSE for software engineering practitioners was 'To provide opportunities for participation by software practitioners.'

**评分器说明**

Both facts are accurate. Tutorial 5 is correctly identified with its title, and the primary submission category for practitioners matches the reference exactly.

### 第 11 行

Which scholars presented the IMPACT project on safety-critical systems and software inspections, reviews, and walkthroughs at the ICSE 2002 conference?

**模型输出**

The scholars who presented the IMPACT project on safety-critical systems and software inspections, reviews, and walkthroughs at ICSE 2002 were:

**Session Chairs:**
- Oliver Laitenberger, Fraunhofer Institute for Experimental Software Engineering
- Dieter Rombach, Fraunhofer Institute for Experimental Software Engineering

**Contributors:**
- Marcus Ciolkowski, University of Kaiserslautern and Fraunhofer Institute for Experimental Software Engineering
- Oliver Laitenberger, Fraunhofer Institute for Experimental Software Engineering
- Dieter Rombach, Fraunhofer Institute for Experimental Software Engineering
- Forrest Shull, Fraunhofer Center for Experimental Software Engineering
- Dewayne Perry, University of Texas, Austin

This was session S7.3 titled "Software Inspections, Reviews & Walkthroughs" as part of the IMPACT project presentations at ICSE 2002.

**参考答案**

The IMPACT presentations at ICSE 2002 were headed by John Knight on safety-critical systems and Oliver Laitenberger on software inspections, reviews, and walkthroughs.

**评分器说明**

Reference states John Knight headed the safety-critical systems presentation and Oliver Laitenberger headed the inspections/reviews/walkthroughs presentation. Prediction omits John Knight entirely and lists multiple contributors without identifying the actual presenters who headed each session.

### 第 12 行

What was the specific schedule for the social event held on the evening after the ACL 2023 best paper awards ceremony?

**模型输出**

The Best Paper Awards ceremony was held on Monday, July 10th from 16:00 to 17:30. The social event that evening was called "Spotlights" and ran from 19:00 to 21:00.

Note: There was also a separate "Social Event" on Tuesday, July 11th (18:30-22:00) at Steam Whistle Brewing, but that was the evening after the Dr. Dragomir Radev Memorial and Business Meeting, not directly after the Best Paper Awards ceremony.

**参考答案**

The social event was scheduled from 7:00 PM to 10:30 PM on July 11th.

**评分器说明**

Prediction states the social event after the awards ceremony was on July 10th (19:00-21:00), but reference specifies July 11th (19:00-22:30). Wrong date and end time.

### 第 14 行

During The Web Conference 2024, which keynote speaker is addressing the challenges posed by AI deepfakes, and on what thematic special day of the conference does the discussion on Large Language Models (LLMs) take place?

**模型输出**

Based on the website content:

1. **Keynote speaker addressing AI deepfakes:** Professor Jeannie Marie Paterson from the Centre for AI and Digital Ethics at the University of Melbourne is delivering a keynote titled "AI deepfakes on the Web: the 'wicked' challenges for AI ethics, law and technology" on Friday, May 17, 2024.

2. **Large Language Models special day:** The discussion on Large Language Models takes place on **Large Language Model Day, which is held on May 14, 2024**. This dedicated full-day event focuses on recent progress in foundational LLMs and building trustworthy LLMs, featuring speakers discussing topics like safety, reasoning capabilities, and the geopolitics of AI.

**参考答案**

Jeannie Marie Paterson addresses AI deepfakes on May 17, 2024. Large Language Model Day is on May 14, 2024.

**评分器说明**

Both facts are present and accurate: Jeannie Marie Paterson addresses AI deepfakes on May 17, 2024, and LLM Day is May 14, 2024. Extra context provided does not contradict the reference.

### 第 50 行

Which specific theme day does the tutorial schedule overlap with at The Web Conference 2024?

**模型输出**

The tutorial schedule overlaps with **Online Trust & Safety Day** on Monday, May 13, 2024.

All tutorials on May 13 (both morning and afternoon sessions) occur on the same day as Online Trust & Safety Day, one of the three theme days at The Web Conference 2024. The other two theme days—Large Language Model Day and Health Day—both take place on May 14, 2024, when the remaining tutorials are scheduled.

**参考答案**

Online Trust & Safety Day

**评分器说明**

Prediction correctly identifies 'Online Trust & Safety Day' as the theme day overlapping with tutorials, matching the reference exactly.

### 第 76 行

What are the submission deadlines for technical papers and the doctoral symposium at the ICSE 2002 conference?

**模型输出**

The ICSE 2002 website does not provide specific submission deadlines for technical papers or the doctoral symposium. The submissions page (https://www.icse-conferences.org/2002/cfp/index.html) lists both "Technical Papers" and "Doctoral Symposium Applications" as submission categories and references "submission deadlines" and "Conference Deadlines," but no actual dates are shown on the page. The linked deadline information appears to be missing or was never published on this archived version of the site.

**参考答案**

The technical paper submission deadline was September 25, 2001, and the doctoral symposium submission deadline was January 6, 2002.

**评分器说明**

Prediction claims deadlines are not provided or missing, but reference shows specific dates were available: technical papers Sept 25, 2001 and doctoral symposium Jan 6, 2002.

### 第 435 行

In ACL 2023, who are the Tutorial Chairs and Main Conference Chairs?

**模型输出**

Based on the ACL 2023 Organizing Committee page:

**Tutorial Chairs:**
- Yun-Nung (Vivian) Chen (National Taiwan University, Taiwan)
- Margot Mieskes (University of Applied Sciences, Darmstadt, Germany)
- Siva Reddy (McGill University and Mila, Canada)

**Main Conference Chairs (Program Chairs):**
- Jordan Boyd-Graber (University of Maryland, USA)
- Naoaki Okazaki (Tokyo Institute of Technology, Japan)
- Anna Rogers (IT University of Copenhagen, Denmark)

**参考答案**

Tutorial Chairs: Yun-Nung (Vivian) Chen, Margot Mieskes, Siva Reddy; Main Conference Chairs: Jordan Lee Boyd-Graber, Naoaki Okazaki, Anna Rogers

**评分器说明**

All required names are present and correctly identified. Minor wording differences (program vs main conference chairs, full name Jordan Lee vs Jordan, added affiliations) are harmless additional details that do not contradict the reference.

### 第 452 行

What were the exact dates and the General Chair for the ICSE conference in 2004?

**模型输出**

**Dates:** May 23-28, 2004

**General Chair:** The website does not provide the General Chair information. The ICSE 2004 pages I checked contain the conference dates and location but lack organizing committee details. The site notes that "All original material for ICSE 2004 remains on this website, but it is no longer maintained, so some addresses and links may be out of date."

**参考答案**

The ICSE 2004 conference was held from May 23 to 28, and the General Chair was Anthony Finkelstein.

**评分器说明**

Prediction provides correct dates but fails to identify Anthony Finkelstein as General Chair, which was explicitly requested.

### 第 476 行

What is the deadline for applying for the subsidies offered for travel and accommodation for financially constrained individuals intending to attend workshops at ACL 2023, and when are these workshops scheduled?

**模型输出**

The deadline for applying for travel and accommodation subsidies (as well as other D&I subsidies) for ACL 2023 was **May 31, 2023** (11:59 PM UTC-12:00).

The workshops at ACL 2023 were scheduled for **July 13-14, 2023** (Thursday-Friday), with one additional workshop on July 9, 2023 (Sunday; Tutorial Day).

**参考答案**

The deadline to apply for subsidies is May 31, 2023. The workshops are scheduled for July 13-14, 2023.

**评分器说明**

Prediction contains both required facts: May 31, 2023 deadline and July 13-14, 2023 workshop dates. Additional details (UTC-12:00 timezone, July 9 workshop) are harmless extras and do not contradict the reference.

### 第 477 行

At ACL 2023, which dates are the workshops scheduled for and what is the deadline for applying for travel and accommodation subsidies?

**模型输出**

Based on the ACL 2023 website:

**Workshop Dates:** July 13-14, 2023

**Travel and Accommodation Subsidy Deadline:** May 31, 2023

The workshops are scheduled for the two days following the main conference (July 10-12). The deadline for applying for travel and accommodation subsidies through the Diversity and Inclusion Program was May 31, 2023, with notification of acceptance by June 11, 2023.

**参考答案**

Workshops at ACL 2023 are scheduled for July 13-14, 2023. The deadline to apply for travel and accommodation subsidies is May 31, 2023.

**评分器说明**

Both required facts are present: workshops on July 13-14, 2023 and subsidy deadline May 31, 2023. Extra context about main conference dates and notification timeline is harmless.

